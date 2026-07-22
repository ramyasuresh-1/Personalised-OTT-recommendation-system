const API_BASE_URL = 'http://localhost:8000';

// Global variables
let driftChartInstance = null;
let currentRatingSelected = 3.0;
let ratingMovieId = null;

// DOM Elements
const userSelect = document.getElementById('user-select');
const movieGrid = document.getElementById('movie-grid');
const modelVersionTag = document.getElementById('model-version-tag');
const systemStatus = document.getElementById('system-status');
const statusText = document.getElementById('status-text');

// Metrics
const metricLatency = document.getElementById('metric-latency');
const metricRequests = document.getElementById('metric-requests');
const metricRatings = document.getElementById('metric-ratings');
const metricDrift = document.getElementById('metric-drift');

// Controls
const btnDriftNeg = document.getElementById('btn-drift-neg');
const btnDriftPos = document.getElementById('btn-drift-pos');
const btnRetrain = document.getElementById('btn-retrain');
const pipelineStatus = document.getElementById('pipeline-status');
const progressContainer = document.getElementById('progress-container');
const progressFill = document.getElementById('progress-fill');
const consoleLogs = document.getElementById('console-logs');
const btnClearConsole = document.getElementById('btn-clear-console');

// Modal Elements
const ratingModal = document.getElementById('rating-modal');
const modalMovieTitle = document.getElementById('modal-movie-title');
const modalStars = document.querySelectorAll('.star-btn');
const ratingNumLabel = document.getElementById('rating-num-label');
const modalSubmit = document.getElementById('modal-submit');
const modalCancel = document.getElementById('modal-cancel');
const modalClose = document.getElementById('modal-close');

// Core Initialize
document.addEventListener('DOMContentLoaded', () => {
    logToConsole('System UI starting up...', 'system');
    initChart();
    
    // Event listeners
    userSelect.addEventListener('change', loadRecommendations);
    btnClearConsole.addEventListener('click', () => {
        consoleLogs.innerHTML = '';
        logToConsole('Console log cleared.', 'system');
    });
    
    // Simulate drift buttons
    btnDriftNeg.addEventListener('click', () => simulateDrift('negative'));
    btnDriftPos.addEventListener('click', () => simulateDrift('positive'));
    btnRetrain.addEventListener('click', triggerRetrain);
    
    // Modal events
    setupModalEvents();
    
    // Initial fetch
    loadRecommendations();
    pollMetrics();
    
    // Refresh metrics telemetry every 3 seconds
    setInterval(pollMetrics, 3000);
});

// Write to Dashboard Console
function logToConsole(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const logLine = document.createElement('div');
    logLine.className = `log-line ${type}`;
    logLine.innerHTML = `[${timestamp}] ${message}`;
    consoleLogs.appendChild(logLine);
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

// Fetch Recommendations for Active User
async function loadRecommendations() {
    const userId = userSelect.value;
    movieGrid.innerHTML = `
        <div class="loading-state">
            <i class="fa-solid fa-circle-notch fa-spin"></i>
            <p>Gathering personalized recommendations...</p>
        </div>
    `;
    
    logToConsole(`Requesting recommendations for User ID ${userId}...`, 'info');
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/recommend?user_id=${userId}`);
        if (!response.ok) throw new Error('API server unavailable');
        
        const data = await response.json();
        
        // Log telemetry
        logToConsole(`API Response: 200 OK. Latency: ${data.latency_ms}ms. Model Version: ${data.model_version}`, 'api');
        
        renderMovies(data.recommendations);
        modelVersionTag.innerText = data.model_version;
        
    } catch (error) {
        logToConsole(`Recommendation Error: ${error.message}`, 'error');
        movieGrid.innerHTML = `
            <div class="error-state">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p>Failed to retrieve recommendations. Is the backend running?</p>
            </div>
        `;
    }
}

// Render movie list
function renderMovies(movies) {
    if (!movies || movies.length === 0) {
        movieGrid.innerHTML = `
            <div class="error-state">
                <i class="fa-solid fa-film"></i>
                <p>No recommendations generated for this profile.</p>
            </div>
        `;
        return;
    }
    
    movieGrid.innerHTML = movies.map(movie => {
        // Assign color classes based on genre for aesthetics
        const genreClass = movie.genre.toLowerCase().replace('/', '-');
        
        return `
            <div class="movie-card" onclick="openRatingModal(${movie.id}, '${movie.title.replace(/'/g, "\\'")}')">
                <div class="poster-art ${genreClass}">
                    <span class="genre-badge">${movie.genre}</span>
                    <i class="fa-solid fa-video"></i>
                </div>
                <div class="movie-info">
                    <span class="movie-title">${movie.title}</span>
                    <div class="movie-meta-row">
                        <span>${movie.year}</span>
                        <span class="movie-rating"><i class="fa-solid fa-star"></i> ${movie.rating.toFixed(1)}</span>
                    </div>
                    <button class="rate-prompt-btn">
                        <i class="fa-regular fa-star"></i> Rate Title
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Chart.js init
function initChart() {
    const ctx = document.getElementById('drift-chart').getContext('2d');
    driftChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Low (1-2★)', 'Mediocre (2.5-3★)', 'Good (3.5-4★)', 'Very Good (4.5★)', 'Excellent (5★)'],
            datasets: [
                {
                    label: 'Baseline (Model Training)',
                    data: [0, 0, 0, 0, 0],
                    backgroundColor: 'rgba(99, 102, 241, 0.4)',
                    borderColor: '#6366f1',
                    borderWidth: 1
                },
                {
                    label: 'Runtime Logs (Recent)',
                    data: [0, 0, 0, 0, 0],
                    backgroundColor: 'rgba(236, 72, 153, 0.4)',
                    borderColor: '#ec4899',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 11 } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8', precision: 0 }
                }
            }
        }
    });
}

// Poll MLOps Telemetry Metrics
async function pollMetrics() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/monitoring/metrics`);
        if (!response.ok) throw new Error('Unresponsive');
        
        const data = await response.json();
        
        // Update stats
        metricLatency.innerText = `${data.telemetry.avg_latency_ms} ms`;
        metricRequests.innerText = data.telemetry.total_inferences;
        metricRatings.innerText = data.telemetry.total_ratings;
        metricDrift.innerText = data.drift_score.toFixed(4);
        
        // Update system health tags
        updateSystemHealthUI(data.drift_status, data.drift_message);
        
        // Update pipeline state
        if (data.is_retraining) {
            pipelineStatus.className = 'pipeline-status running';
            pipelineStatus.innerText = 'Retraining Model';
            btnRetrain.disabled = true;
        } else {
            pipelineStatus.className = 'pipeline-status';
            pipelineStatus.innerText = 'Idle';
            btnRetrain.disabled = false;
        }
        
        // Update Charts
        if (driftChartInstance && data.ratings_distribution) {
            driftChartInstance.data.datasets[0].data = data.ratings_distribution.baseline;
            driftChartInstance.data.datasets[1].data = data.ratings_distribution.recent;
            driftChartInstance.update();
        }
        
    } catch (error) {
        systemStatus.className = 'system-status-pill status-drifted';
        statusText.innerText = 'Offline';
    }
}

function updateSystemHealthUI(status, message) {
    if (status === 'Healthy') {
        systemStatus.className = 'system-status-pill status-healthy';
        statusText.innerText = 'Healthy';
    } else if (status === 'Warning') {
        systemStatus.className = 'system-status-pill status-warning';
        statusText.innerText = 'Drift Warning';
    } else {
        systemStatus.className = 'system-status-pill status-drifted';
        statusText.innerText = 'Drifted';
    }
}

// Force Ratings Drift Simulation
async function simulateDrift(skewType) {
    logToConsole(`Simulating drift event: Injection of ratings with ${skewType} skew...`, 'warning');
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/simulate-drift`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skew_type: skewType })
        });
        
        const data = await response.json();
        logToConsole(`Drift Simulation: ${data.message}`, 'success');
        
        // Immediately fetch updated metrics
        pollMetrics();
        
    } catch (error) {
        logToConsole(`Failed to trigger drift simulation: ${error.message}`, 'error');
    }
}

// Trigger Pipeline Retraining
async function triggerRetrain() {
    logToConsole('Triggering automated ML retraining pipeline...', 'system');
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/retrain`, { method: 'POST' });
        const data = await response.json();
        
        logToConsole(`Retraining: ${data.message}`, 'success');
        
        // Show simulated visual progress matching the 4s API sleep duration
        startProgressBar();
        pollMetrics();
        
    } catch (error) {
        logToConsole(`Failed to trigger retraining: ${error.message}`, 'error');
    }
}

function startProgressBar() {
    progressContainer.style.display = 'block';
    progressFill.style.width = '0%';
    
    let currentProgress = 0;
    const intervalTime = 100; // ms
    const totalDuration = 4000; // ms (matching backend sleep)
    const steps = totalDuration / intervalTime;
    const progressPerStep = 100 / steps;
    
    const interval = setInterval(() => {
        currentProgress += progressPerStep;
        progressFill.style.width = `${Math.min(currentProgress, 100)}%`;
        
        if (currentProgress >= 100) {
            clearInterval(interval);
            setTimeout(() => {
                progressContainer.style.display = 'none';
                logToConsole('Model Retrained successfully. SVD components refitted and active.', 'success');
                // Reload recommendations to see updated model output
                loadRecommendations();
                pollMetrics();
            }, 500);
        }
    }, intervalTime);
}

// Modal handling
function setupModalEvents() {
    modalStars.forEach(star => {
        star.addEventListener('mouseover', function() {
            highlightStars(this.dataset.star);
        });
        
        star.addEventListener('click', function() {
            currentRatingSelected = parseFloat(this.dataset.star);
            ratingNumLabel.innerText = currentRatingSelected.toFixed(1);
            setSelectedStars(currentRatingSelected);
        });
    });
    
    modalStars[0].parentElement.addEventListener('mouseleave', () => {
        setSelectedStars(currentRatingSelected);
    });
    
    modalClose.addEventListener('click', () => ratingModal.style.display = 'none');
    modalCancel.addEventListener('click', () => ratingModal.style.display = 'none');
    modalSubmit.addEventListener('click', submitRating);
}

function openRatingModal(movieId, movieTitle) {
    ratingMovieId = movieId;
    modalMovieTitle.innerText = movieTitle;
    currentRatingSelected = 3.0;
    ratingNumLabel.innerText = '3.0';
    setSelectedStars(3);
    ratingModal.style.display = 'flex';
}

function highlightStars(count) {
    modalStars.forEach((star, index) => {
        if (index < count) {
            star.className = 'fa-solid fa-star star-btn active';
        } else {
            star.className = 'fa-regular fa-star star-btn';
        }
    });
}

function setSelectedStars(count) {
    modalStars.forEach((star, index) => {
        if (index < count) {
            star.className = 'fa-solid fa-star star-btn active';
        } else {
            star.className = 'fa-regular fa-star star-btn';
        }
    });
}

async function submitRating() {
    const userId = userSelect.value;
    logToConsole(`Submitting feedback rating: User ${userId} gave Movie ${ratingMovieId} a ${currentRatingSelected}★ rating...`, 'info');
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/rate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: parseInt(userId),
                movie_id: ratingMovieId,
                rating: currentRatingSelected
            })
        });
        
        const data = await response.json();
        logToConsole(`Feedback Recorded: ${data.message}`, 'success');
        ratingModal.style.display = 'none';
        
        // Refresh
        pollMetrics();
        loadRecommendations();
        
    } catch (error) {
        logToConsole(`Feedback submission failed: ${error.message}`, 'error');
    }
}
