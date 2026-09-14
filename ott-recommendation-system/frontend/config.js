window.APP_CONFIG = window.APP_CONFIG || {};
const storedApiBase = localStorage.getItem('ott_api_base_url');
const localApiBase = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
	? `${window.location.protocol}//${window.location.hostname}:8000`
	: '';
const configuredApiBase = window.APP_CONFIG.API_BASE_URL || window.__APP_API_URL__ || localApiBase || storedApiBase;
window.APP_CONFIG.API_BASE_URL = configuredApiBase;
window.APP_CONFIG.APP_NAME = window.APP_CONFIG.APP_NAME || 'AURA OTT';
