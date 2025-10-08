## Note :

You can look in backend folder for main app and readme related to main fastapi backend

---
## 🚀 Quick Start

This project uses a hybrid setup: the database runs in Docker, and the Python application runs locally in a virtual environment.

### 1. Start the Database (Docker)

First, make sure Docker is running. Then, from the project's **root directory** (`portfolio-backend/`), start the MongoDB container:

```bash
# Start the database container in the background
docker compose up -d
````

### 2\. Run the Backend Application (Local)

Next, run the FastAPI server in a separate terminal.

```bash
# Navigate to the backend code directory
cd backend

# Activate the Python virtual environment
source venv/bin/activate

# Start the server with hot-reloading
uvicorn main:app --reload
```

-----

## 🛠️ Accessing the API

Once the server is running, you can access the following endpoints:

  * **Interactive API Docs (Swagger UI):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
  * **Health Check:** [http://127.0.0.1:8000/api/health](https://www.google.com/search?q=http://127.0.0.1:8000/api/health)

-----

## 🗄️ Database Management

### Connecting with a GUI (MongoDB Compass)

You can connect to your Dockerized database using the following connection string in MongoDB Compass:

```
mongodb://localhost:27017/
```

### Useful Docker Commands

Manage the MongoDB container from the project's **root directory**.

  * **Check Status:** See which containers are running.
    ```bash
    docker compose ps
    ```
  * **Stop Container:** "Pauses" the database to save resources. Your data is safe.
    ```bash
    docker compose stop
    ```
  * **Start a Stopped Container:**
    ```bash
    docker compose start
    ```
  * **Stop and Remove Container:** Shuts down and removes the container. Your data is still safe in the volume.
    ```bash
    docker compose down
    ```
  * **⚠️ Nuke Everything:** Stops and removes the container AND **deletes all database data**. Use this for a complete reset.
    ```bash
    docker compose down -v
    ```
