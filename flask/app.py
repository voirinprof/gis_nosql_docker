# import the necessary libraries
from flask import Flask, jsonify, request
from redis import Redis
from neo4j import GraphDatabase
import os
import geopandas as gpd
import pyproj
from shapely.geometry import LineString
import logging
from logging.handlers import RotatingFileHandler
import json

app = Flask(__name__)

# Configuration du logging
logger = logging.getLogger('flask_app')
logger.setLevel(logging.DEBUG)

# Formatter pour les messages de log
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Handler pour la console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Handler pour le fichier (avec rotation pour limiter la taille)
file_handler = RotatingFileHandler('/app/logs/app.log', maxBytes=1000000, backupCount=5)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# the address file for the redis
qc_addresses_file = os.environ.get('DATA_ADDRESS')
# the streets file for neo4j
qc_streets_file = os.environ.get('DATA_STREETS')

# connection to redis
redis_client = Redis(host=os.environ.get('REDIS_HOST'), port=os.environ.get('REDIS_PORT'), decode_responses=True)

# Connection to Neo4j
neo4j_uri = os.environ.get('NEO4J_URI')
neo4j_user = os.environ.get('NEO4J_USER')
neo4j_password = os.environ.get('NEO4J_PASSWORD')
driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

# read the shapefile using geopandas
streets_shp = gpd.read_file(qc_streets_file)
# reproject the GeoDataFrame to EPSG:4326
streets_shp = streets_shp.to_crs(epsg=4326)


# Initialize some example data on startup
def init_redis_data():
    data_qc_address = gpd.read_file(qc_addresses_file)

    logger.debug('Initializing Redis data with addresses')
    for index, rows in data_qc_address.iterrows():
        address = rows['ADRESSE']
        geometry = rows['geometry']
        coords = geometry.coords

        redis_client.geoadd("locations", (coords[0][0], coords[0][1], address))
        # Ajoutez également l'adresse à un ensemble trié pour l'index
        redis_client.zadd("index_locations", {address: 1})


# Run initialization only if the key doesn't exist
if not redis_client.exists("locations"):
    init_redis_data()

# Initialize Neo4j data
def init_neo4j_data():
    logger.debug('Initializing Neo4j data with nodes and streets')
    # nodes
    # header = ['id:ID', 'latitude:FLOAT', 'longitude:FLOAT']
    # streets
    # header = [':START_ID', ':END_ID', 'name', 'objectid:INT', 'geometry', 'length:FLOAT', 'speed:FLOAT']
    with driver.session() as session:
        session.run("""
            CALL apoc.import.csv(
            [{fileName: 'file:/nodes.csv', labels: ['Node']}],
            [{fileName: 'file:/streets.csv', type: 'Link'}],
            {delimiter: ',', stringIds: false}
            )
        """)

        logger.info("Nodes and streets imported from CSV files")
        # we create the graph projection
        session.run("""
            CALL gds.graph.project(
                'myGraphRoad',
                'Node',
                'Link',
                {
                    relationshipProperties: ['length', 'objectid']
                }
            )
            """)
        logger.info("Graph projection 'myGraphRoad' created")


# Exécuter l'initialisation une seule fois au démarrage
with driver.session() as session:
    result = session.run("MATCH (n) RETURN count(n) AS count").single()
    logger.debug(f"result: {result}")
    if result["count"] == 0:
        # if the database is empty, we initialize the data
        init_neo4j_data()
        # if you want to delete all the nodes and relationships
        # session.run("MATCH (n) DETACH DELETE n")
        # if you want drop the graph projection
        # session.run("CALL gds.graph.drop('myGraphRoad') YIELD graphName RETURN graphName")

# function to search for addresses in Redis
def addressSearch(query):

    # Use the zscan command to iterate over the sorted set index
    matches = []
    for match in redis_client.zscan_iter("index_locations"):
        match_str = match[0]
        if match_str.startswith(query):
            matches.append(match_str)
    suggestions = []
    for match in matches:
        adresse = match
        coordonnees = redis_client.geopos("locations", adresse)
        if coordonnees:
            lat = coordonnees[0][1]
            lon = coordonnees[0][0]
            suggestions.append({"display_name": adresse, "lat": lat, "lon": lon})

    return suggestions

# function to search for nodes in Neo4j
def nodeSearch(latitude, longitude):
    
    # use the point function to create a point and find the closest nodes
    requete_cypher = """
    MATCH (c:Node)
    WITH c, point({latitude: $lat, longitude: $lon}) AS refPoint
    WITH c, point.distance(point({latitude: c.latitude, longitude: c.longitude}), refPoint) AS distance
    WHERE distance <= $max_distance
    RETURN c.id, c.longitude, c.latitude, distance
    ORDER BY distance

    """
    locations = []
    with driver.session() as session:
        # execute the Cypher query and get the result as a list of dictionaries
        result = session.run(requete_cypher, lat=float(latitude), lon=float(longitude), max_distance=500)
        
        # loop over the result and extract the locations
        locations = [
                {
                    
                    "id": record["c.id"],
                    "longitude": record["c.longitude"],
                    "latitude": record["c.latitude"],
                    "distance": record["distance"]
                }               
                for record in result
            ]
        return locations


# Define the Flask routes
# home route
@app.route('/', methods=['GET'])
def home():
    return {"status": "healthy"}, 200

# route to get the address suggestions
@app.route("/suggest")
def suggest():
    query = request.args.get("q", "").lower()
    if not query or len(query) < 2:
        return jsonify([])

    search_results = redis_client.zrangebylex("index_locations", f"[{query}", f"[{query}\xff")

    suggestions = [
        {"label": addr}
        for addr in search_results
        if query in addr.lower()
    ][:10] 

    return jsonify(suggestions)

# route to get the location of the address
@app.route("/location")
def location():
    query = request.args.get("q", "")
    if not query or len(query) < 2:
        return jsonify([])

    # call the addressSearch function
    suggestions = addressSearch(query)

    return jsonify(suggestions)

# route to get the node 
@app.route("/findnode")
def findnode():
    latitude = request.args.get("lat", "")
    longitude = request.args.get("lon", "")
    if not latitude or not longitude:
        return jsonify([])
    # call the nodeSearch function
    locations = nodeSearch(latitude, longitude)

    return jsonify(locations)

# route to get the path between two addresses
@app.route("/findpath")
def findpath():
    # get the start and end addresses from the request
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    if not start or not end :
        return jsonify([])
    # find the closest address to the start and end addresses
    suggest_start = addressSearch(start)
    suggest_end = addressSearch(end)
    
    # we will use the first address found
    if len(suggest_start) > 0:
        first = suggest_start[0]
        # find the closest node to the address    
        suggest_node_start = nodeSearch(first['lat'], first['lon'])
    
    # we will use the first address found
    if len(suggest_end) > 0:
        first = suggest_end[0]
        # find the closest node to the address
        suggest_node_end = nodeSearch(first['lat'], first['lon'])
    
    # we will use the first node found
    if len(suggest_node_start) > 0:
        first_node = suggest_node_start[0]
    # we will use the first node found
    if len(suggest_node_end) > 0:
        second_node = suggest_node_end[0]

        
    logger.debug(f"first_node: {first_node} ")
    logger.debug(f"second_node: {second_node} ")

    # we will find the path between the two nodes
    requete_cypher_chemin = """
    MATCH
    (a:Node {id: """+str(first_node['id'])+"""}),
    (b:Node {id: """+str(second_node['id'])+"""})
    CALL gds.shortestPath.dijkstra.stream('myGraphRoad', {
        sourceNode: a,
        targetNode: b,
        relationshipWeightProperty: 'length'
    })
    YIELD index, sourceNode, targetNode, totalCost, nodeIds, costs, path
    RETURN
    index,
    gds.util.asNode(sourceNode).id AS sourceNodeName,
    gds.util.asNode(targetNode).id AS targetNodeName,
    totalCost,
    [nodeId IN nodeIds | gds.util.asNode(nodeId).id] AS nodeNames,
    costs, nodes(path) as path

    """

    with driver.session() as session:
        # execute the Cypher query and get the result as a list of dictionaries
        resultat_chemin = session.run(requete_cypher_chemin).single()

        # get nodeNames -> [1971, ...]
        # get totalCost

        totalCost = resultat_chemin["totalCost"]
        nodeNames = resultat_chemin["nodeNames"]
        

        logger.debug(f"nodeNames: {len(nodeNames)} ")
        logger.debug(f"totalCost: {totalCost} ")

        # get the objectid of the path (for the real path)
        objectids = []

        # loop over nodeNames
        for index, node in enumerate(nodeNames[:-1]):
            # get the objectid of the path
            resu = session.run("MATCH (a:Node {id: "+str(node)+"})-[r]->(b:Node {id: "+str(nodeNames[index+1])+"}) RETURN r, r.objectid").single()
                
            objectids.append(resu['r.objectid'])
        # keep only the streets that are in the objectids
        data_path = streets_shp[streets_shp['OBJECTID'].isin(objectids)] 
        
        # convert the geometry to a LineString
        geojson_obj = json.loads(data_path.to_json())

        # return the result
        return jsonify({"objectids": objectids, "geojson": geojson_obj, "totalCost": totalCost, "nodeNames": nodeNames})



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)