# AURA - Personalized OTT Recommendation & MLOps System

AURA is an end-to-end, interactive movie recommendation platform and MLOps telemetry dashboard. It demonstrates how to combine **Collaborative Filtering** with **data drift monitoring, background retraining pipelines, containerized deployment, and CI/CD pipelines**.

---

## 🚀 Key Features
1. **Personalized Recommendations**: Matrix Factorization (Truncated SVD) collaborative filtering model mapped to distinct user preferences.
2. **Cold-Start Fallback**: Popularity-weighted scoring for new users or systems without enough rating logs.
3. **Real-time Telemetry**: Active inference counter, running latency measurement, rating feedback logging.
4. **Data Drift Detection**: Automated Population Stability Index (PSI) tracking that evaluates the difference between training-time ratings distribution and live production logs.
5. **On-Demand Retraining**: API-driven background retraining worker that refits the collaborative filtering model and hot-swaps it in-memory.
6. **One-Command Deployment**: Clean multi-container deployment configured via Docker Compose.
7. **CI/CD Pipeline**: GitHub Actions workflow verifying Python linting (`flake8`), unit testing (`pytest`), and Docker build validity.

---

## 🛠 Tech Stack
- **Frontend UI**: Semantic HTML5, Custom Vanilla CSS (Glassmorphism dark mode), JavaScript (Chart.js for monitoring).
- **Backend Service**: Python 3.10+, FastAPI (Asynchronous API), SQLite (Datastore), Uvicorn.
- **Machine Learning**: Scikit-Learn (SVD & Popularity metrics), Pandas, Numpy.
- **DevOps & Containers**: Docker, Docker Compose, Nginx (Frontend Web Server).

---

## 📦 Getting Started (Local Run)

You can run AURA locally either using Python directly or using Docker Compose.

### Option A: Running Directly (Recommended for Development)

#### 1. Setup Backend
Open a terminal in the `backend/` directory:
```bash
# Create a virtual environment
python -m venv venv
source venv/Scripts/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run FastAPI server
uvicorn app.main:app --reload --port 8000
```
The API docs will be live at `http://localhost:8000/docs`.

#### 2. Open Frontend
Simply double-click the `frontend/index.html` file to open the dashboard in any browser, or serve it using an extension like VS Code Live Server.

---

### Option B: Running with Docker Compose (Single Command)

From the project root directory:
```bash
docker-compose up --build
```
- **Frontend Dashboard**: Open `http://localhost` in your browser.
- **Backend API**: Open `http://localhost:8000`.
- **MLflow Tracking UI**: Open `http://localhost:5000` to inspect experiments, runs, parameters, metrics, and artifact history.

> Note: The project uses a local SQLite-backed MLflow tracking store in `backend/mlflow.db` and `backend/mlruns` for artifacts.

---

## 🧪 Interactive Walkthrough (How to test Drift & Retraining)

AURA has built-in simulation tools to let you verify the retraining pipeline easily:

1. **Get Recommendations**: Open the dashboard, choose **User 1 (Sci-Fi lover)** or **User 16 (Drama fan)** from the dropdown. Note the personalized genres in the cards.
2. **Check Health**: Look at the **MLOps Monitoring Suite** panel on the right. Under normal operations, the **Drift Index (PSI)** is very low (< 0.1), and status is **Healthy** (Green pulse).
3. **Simulate User Feedback Drift**:
   - Click the **"Force Rating Drop"** button. This simulates a real-world drift scenario by injecting 100+ low-rating reviews (1.0 - 2.0 stars) into the telemetry base.
   - The serving distribution shifts dramatically from baseline training. The **Drift Index (PSI) spikes above 0.25** and status transitions to **Drifted (Red alert)**.
4. **Execute Retraining Pipeline**:
   - Click **"Trigger Retraining"**.
   - A background retraining job is spawned. A progress bar tracks the matrix factorization re-fitting.
   - Once completed, SVD weights are hot-swapped in memory, the metrics dashboard refreshes, and the Drift Index returns to **Healthy**.
