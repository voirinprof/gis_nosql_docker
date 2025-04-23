# import the necessary libraries
import geopandas as gpd
from shapely.geometry import LineString, Point

# file with streets
filename = '/data/Segments_de_rue.shp'

# read the shapefile using geopandas
gdf = gpd.read_file(filename)
# reproject the GeoDataFrame to EPSG:3857
gdf_3857 = gdf.to_crs(epsg=3857)

# we need to create a dictionary of nodes and a list of streets
# for the graph
# nodes = {(lon,lat): id, ...}
nodes = {}
# streets = [[start, end, street, objectid, geometry, length, speed]]
streets = []

cnt = 0
# loop over the rows of the GeoDataFrame
for index, row in gdf_3857.iterrows():
    # print the type of geometry
    street = row['TOPONYMIE']
    geometry = row['geometry']
    objectid = row['OBJECTID']
    speed = row['VITESSE']
    
    if isinstance(geometry, LineString):
        # if the geometry is a LineString, we can use it directly
        linestring = geometry
    # get the first and last points of the LineString
    lon_start, lat_start = linestring.coords[0]
    lon_end, lat_end = linestring.coords[-1]
    # add a value to the dictionary for each point
    # key = (lon, lat)
    # value = id
    if (lon_start, lat_start) not in nodes:
        nodes[(lon_start, lat_start)] = cnt
        cnt += 1
    if (lon_end, lat_end) not in nodes:
        nodes[(lon_end, lat_end)] = cnt
        cnt += 1
    # get the id of the start and end points
    start_pt = -1
    end_pt = -1
    if (lon_start, lat_start) in nodes:
        start_pt = nodes[(lon_start, lat_start)]
    if (lon_end, lat_end) in nodes:
        end_pt = nodes[(lon_end, lat_end)]
    
    if start_pt != -1 and end_pt != -1:
        # add the street to the list of streets
        length = linestring.length
        streets.append([start_pt, end_pt, street, objectid, geometry, length, speed])
        
print(f"Number of nodes: {len(nodes)}")
print(f"Number of streets: {len(streets)}")

# save node as geojson
# nodes = {(lon,lat): id, ...}
nodes_tmp = []
for (lon, lat), id in nodes.items():
    
    point = Point(lon, lat)
    nodes_tmp.append({'geometry': point, 'id:ID': id})

gdf_nodes = gpd.GeoDataFrame(nodes_tmp, columns=['geometry', 'id:ID'], geometry='geometry', crs='EPSG:3857')
# reproject the GeoDataFrame to EPSG:4326 for the graph
gdf_nodes = gdf_nodes.to_crs(epsg=4326)

# create column latitude and longitude
gdf_nodes['latitude:FLOAT'] = gdf_nodes['geometry'].y
gdf_nodes['longitude:FLOAT'] = gdf_nodes['geometry'].x
# save [id, latitude, longitude] to csv
gdf_nodes[['id:ID', 'latitude:FLOAT', 'longitude:FLOAT']].to_csv('/data/nodes.csv', index=False)


# create a GeoDataFrame from the list of streets
streets_tmp = []
for start_pt, end_pt, street, objectid, geometry, length, speed in streets:
    # create a edge for each street (bidirectional)
    streets_tmp.append({'geometry': geometry, ':START_ID': start_pt, ':END_ID': end_pt, 'street': street, 'objectid:INT': objectid, 'length:FLOAT': length, 'speed:FLOAT': speed})
    streets_tmp.append({'geometry': geometry, ':START_ID': end_pt, ':END_ID': start_pt, 'street': street, 'objectid:INT': objectid, 'length:FLOAT': length, 'speed:FLOAT': speed})
gdf_streets = gpd.GeoDataFrame(streets_tmp, columns=['geometry', ':START_ID', ':END_ID', 'street', 'objectid:INT', 'length:FLOAT', 'speed:FLOAT'], geometry='geometry', crs='EPSG:3857')
# save [start_pt, end_pt, street, objectid, length, speed] to csv
gdf_streets[[':START_ID', ':END_ID', 'street', 'objectid:INT', 'length:FLOAT', 'speed:FLOAT']].to_csv('/data/streets.csv', index=False)