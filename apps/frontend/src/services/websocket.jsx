import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { auth } from './auth';

const WebSocketContext = createContext(null);

export const useWebSocket = () => useContext(WebSocketContext);

export const WebSocketProvider = ({ children }) => {
  const [onlineDevices, setOnlineDevices] = useState(new Set());
  const [connectionStatus, setConnectionStatus] = useState('offline');
  const [lastMessage, setLastMessage] = useState(null);
  const wsRef = useRef(null);

  const connect = useCallback((deviceId) => {
    const token = auth.getToken();
    if (!token || !deviceId) return;

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    setConnectionStatus('connecting');
    const wsUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    
    // In dev, the proxy handles /ws
    const ws = new WebSocket(`${wsUrl}//${host}/ws/${deviceId}?token=${token}`);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnectionStatus('connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLastMessage(data);

        if (data.type === 'device_status') {
          setOnlineDevices(prev => {
            const next = new Set(prev);
            if (data.status === 'online') {
              next.add(data.device_id);
            } else {
              next.delete(data.device_id);
            }
            return next;
          });
        }
      } catch (err) {
        console.error('Error parsing WS message', err);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setConnectionStatus('offline');
      setTimeout(() => connect(deviceId), 5000); // Reconnect attempt
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected — cannot send message');
    }
  }, []);

  return (
    <WebSocketContext.Provider value={{ onlineDevices, connectionStatus, lastMessage, connect, disconnect, sendMessage }}>
      {children}
    </WebSocketContext.Provider>
  );
};
