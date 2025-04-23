# 🗺️ GIS NoSQL Docker

This project provides a Dockerized architecture to:

- Generate CSV files from a Shapefile using a Python script
- Import those files into a Neo4j graph database and a Redis database
- Use Redis database for suggestion of address in the input
- Visualize the road network using a Flask web application (path between 2 points)

---

## 📁 Project Structure

```
gis_nosql_docker/
├── creator/                # Service that generates CSV files
│   ├── createnetwork.py    # Script that processes the Shapefile
│   └── Dockerfile          # Dockerfile for the creator service
├── flask/                  # Flask web app
│   ├── app.py              # Main Flask application
│   ├── requirements.txt    # Python dependencies
│   └── Dockerfile          # Dockerfile for Flask
├── nginx/                  # Nginx reverse proxy configuration
│   └── nginx.conf
├── web/                    # web page to test the services
│   └── index.html
├── data/                   # Shared data folder (input and output)
│   ├── roads.shp           # Input Shapefile
│   ├── nodes.csv           # Output: intersections as CSV (for Neo4j)
│   └── streets.csv         # Output: roads as CSV (for Neo4j)
├── docker-compose.yml      # Docker Compose orchestration
└── README.md               # This file
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed

### 2. Clone the repository

```bash
git clone https://github.com/voirinprof/gis_nosql_docker.git
cd gis_nosql_docker
```

### 3. Add your Shapefile

Place your `roads.shp` and its associated files (`.shx`, `.dbf`, etc.) into the `data/` directory.

### 4. Build and run

```bash
docker-compose up --build
```

- The `creator` service will run once to generate `nodes.csv` and `streets.csv` for Neo4j
- The Flask app will then be available at: [http://localhost:5000](http://localhost:5000)

---

## 🧱 Docker Services

| Service   | Description                                       |
|-----------|---------------------------------------------------|
| `creator` | Processes the Shapefile and generates CSV files   |
| `web`     | Flask app that displays the road network          |
| `neo4j`   | Graph database for storing road and intersection data |
| `nginx`   | Optional reverse proxy for serving the Flask app  |

---

## 🔄 Importing Data into Neo4j

Once the CSV files are generated, you can import them into Neo4j using APOC:

```cypher
CALL apoc.import.csv(
  ["file:///nodes.csv"],
  ["file:///streets.csv"],
  {
    ...
  }
);
```
This command is called when the flask api starts, if the Neo4j database does not exist.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.
