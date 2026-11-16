import { auth } from './auth';

const API_BASE_URL = '/api/v1';

async function fetchWithAuth(url, options = {}) {
  const token = auth.getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers,
  });
  
  if (!response.ok) {
    if (response.status === 401) {
      auth.clearTokens();
      window.location.href = '/login';
    }
    const error = await response.json().catch(() => ({ detail: 'API Error' }));
    throw new Error(error.detail || 'API Error');
  }
  
  return response.json();
}

export const api = {
  auth: {
    login: async (email, password) => {
      const data = await fetchWithAuth('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      auth.setTokens(data.access_token, data.refresh_token);
      return data;
    },
    register: async (email, password, displayName) => {
      const data = await fetchWithAuth('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password, display_name: displayName })
      });
      auth.setTokens(data.access_token, data.refresh_token);
      return data;
    },
    me: () => fetchWithAuth('/auth/me'),
  },
  devices: {
    list: () => fetchWithAuth('/devices/'),
    register: (name, fingerprint, platform) => fetchWithAuth('/devices/register', {
      method: 'POST',
      body: JSON.stringify({ device_name: name, device_fingerprint: fingerprint, platform })
    }),
    initiatePairing: (sourceDeviceId) => fetchWithAuth('/devices/pair/initiate', {
      method: 'POST',
      body: JSON.stringify({ source_device_id: sourceDeviceId })
    }),
    completePairing: (code, targetDeviceId) => fetchWithAuth('/devices/pair/complete', {
      method: 'POST',
      body: JSON.stringify({ pairing_code: code, target_device_id: targetDeviceId })
    }),
    delete: (deviceId) => fetchWithAuth(`/devices/${deviceId}`, {
      method: 'DELETE'
    })
  },
  sessions: {
    history: (limit = 50) => fetchWithAuth(`/sessions/history?limit=${limit}`),
    initiate: (sourceDeviceId, targetDeviceId) => fetchWithAuth('/sessions/initiate', {
      method: 'POST',
      body: JSON.stringify({ source_device_id: sourceDeviceId, target_device_id: targetDeviceId })
    }),
    cancel: (transferId) => fetchWithAuth(`/sessions/${transferId}`, {
      method: 'DELETE'
    })
  },
  constellations: {
    list: () => fetchWithAuth('/constellations/'),
    create: (name, deviceId) => fetchWithAuth('/constellations/create', {
      method: 'POST',
      body: JSON.stringify({ name, device_id: deviceId || null })
    }),
    join: (joinCode, deviceId) => fetchWithAuth('/constellations/join', {
      method: 'POST',
      body: JSON.stringify({ join_code: joinCode, device_id: deviceId })
    }),
    get: (constellationId) => fetchWithAuth(`/constellations/${constellationId}`),
    leave: (constellationId, deviceId) => fetchWithAuth(`/constellations/${constellationId}/leave`, {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId })
    })
  }
};
