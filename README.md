 # ⚡ SageNet Energy Backend

 Enterprise-grade IoT Infrastructure for Real-Time Energy Monitoring & Analytics.


![alt text](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)


![alt text](https://img.shields.io/badge/FastAPI-0.95-teal?style=for-the-badge&logo=fastapi)


![alt text](https://img.shields.io/badge/Docker-Enabled-blue?style=for-the-badge&logo=docker)


![alt text](https://img.shields.io/badge/Status-Production-green?style=for-the-badge)


 ## 📖 Overview

 SageNet Backend is the cloud infrastructure powering the SageNet Smart Energy Ecosystem. It is designed with a Microservices-ready architecture to handle high-throughput IoT telemetry, secure device control, and future AI/ML workloads.

 The system follows Zero Trust Security principles, ensuring that every API request is authenticated via JWT and every device command is authorized via strict ownership rules.

 ---

 ## 🏗 Architecture

 The backend is containerized using Docker and orchestrated via Docker Compose. It consists of distinct services to ensure Resilience and Scalability.

 ### 1. The API Gateway (energy_api)
 * Tech: FastAPI (Python), Uvicorn.
 * Role: The "Commander". Handles User Authentication (Firebase), Device Control, and Historical Data retrieval.
 * Security: Protected by Caddy Reverse Proxy (Automatic HTTPS) and Firebase Admin SDK (JWT Validation).

 ### 2. The Telemetry Bridge (energy_bridge)
 * Tech: Paho-MQTT, InfluxDB Client.
 * Role: The "Ingestor". A robust, never-sleeping service that listens to the MQTT Broker.
 * Logic: Enriches raw sensor data with User Metadata (from Firebase) and writes it to the Time-Series Database (InfluxDB).

 ### 3. The Infrastructure
 * Database (Hot): InfluxDB Cloud (Time-series data: Voltage, Current, Power).
 * Database (Cold): Firebase Firestore (Device Metadata, User Relationships).
 * Broker: HiveMQ Cloud (Secure MQTTS Messaging).
 * Proxy: Caddy (SSL Termination & Load Balancing).

 ---

 ## 📂 Directory Structure

 text  smart-energy-backend/  ├── app/ # Main Application Source  │ ├── api/  │ │ └── v1/ # Versioned API Routes  │ │ ├── endpoints/ # Controllers (Devices, Analytics)  │ │ └── api.py # Router Aggregator  │ ├── core/ # System Config & Logging  │ ├── models/ # Pydantic Schemas (Data Validation)  │ ├── services/ # Business Logic (MQTT, Influx, Firebase)  │ ├── main_api.py # FastAPI Entry Point  │ └── main_bridge.py # MQTT Bridge Entry Point  ├── logs/ # Rotating Logs (Access & Errors)  ├── firmware/ # OTA Update Binaries  ├── Caddyfile # Reverse Proxy Configuration  ├── docker-compose.yml # Container Orchestration  └── Dockerfile # Python Runtime definition 

 ---

 ## 🚀 Getting Started (Local Development)

 ### Prerequisites
 * Python 3.10+
 * Docker & Docker Compose
 * serviceAccountKey.json (From Firebase Console)

 ### 1. Environment Setup
 Clone the repository and create your secrets file:

 bash  git clone https://github.com/YourRepo/sagenet-backend.git  cd sagenet-backend  cp .env.example .env 

 Fill in your .env file:
 ini  # MQTT Config  MQTT_BROKER=your-cluster.hivemq.cloud  MQTT_PORT=8883  MQTT_USER=backend_service  MQTT_PASS=secure_password   # Database Config  INFLUX_URL=https://eu-central-1-1.aws.cloud2.influxdata.com  INFLUX_TOKEN=your_token  INFLUX_ORG=your_org  INFLUX_BUCKET=energy_raw   # Firebase  FIREBASE_CRED=serviceAccountKey.json 

 ### 2. Run Locally
 You can run the API directly on your host machine for debugging:

 bash  # Create Virtual Environment  python -m venv venv  source venv/bin/activate # or venv\Scripts\activate on Windows   # Install Dependencies  pip install -r requirements.txt   # Start API  uvicorn app.main_api:app --reload --host 0.0.0.0 --port 8000 

 ---

 ## ☁️ Deployment (Oracle Cloud / VPS)

 The system is designed for Zero-Downtime Deployment using Docker.

 ### 1. Deploy Stack
 Upload the code to your server and run:

 bash  # Build and Detach  docker compose up -d --build 

 ### 2. Verify Services
 Check the health of the containers:

 bash  docker ps  docker logs -f energy_api 

 ---

 ## 📚 API Documentation

 Once running, full interactive Swagger UI documentation is available at:

 * Local: http://localhost:8000/docs
 * Production: https://your-domain.com/docs

 ### Key Endpoints

  Method  Endpoint  Description 
  :---  :---  :--- 
  POST  /api/v1/devices/{id}/control  Toggle Relay ON/OFF (Requires JWT) 
  GET  /api/v1/devices/{id}/history  Fetch historical energy graphs 
  GET  /api/v1/analytics/{id}/bill  Get real-time bill estimation 

 ---

 ## 🛡 Security Protocols

 1. Transport Security: All external traffic is encrypted via SSL/TLS (HTTPS & MQTTS).
 2. Authentication: Users are authenticated via Firebase Auth (Google Identity). Passwords are never stored on our servers.
 3. Authorization: API enforces strict ownership checks. A user can only control devices linked to their User_UID in Firestore.
 4. Network Isolation: The API container is not exposed directly. Traffic must pass through the Caddy Reverse Proxy.

 ---

 ## 🤝 Contributing

 1. Fork the Project
 2. Create your Feature Branch (git checkout -b feature/AmazingFeature)
 3. Commit your Changes (git commit -m 'Add some AmazingFeature')
 4. Push to the Branch (git push origin feature/AmazingFeature)
 5. Open a Pull Request

 ---

 © 2025 SageNet Energy. Built for High Performance.