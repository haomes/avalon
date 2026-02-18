/**
 * WebSocket Client - Auto-reconnecting WebSocket wrapper for the Avalon dashboard
 */
class WebSocketClient {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.handlers = {};           // event type -> [handler, handler, ...]
    this.reconnectDelay = 2000;
    this.maxReconnectDelay = 30000;
    this.reconnectAttempts = 0;
    this.autoReconnect = true;
    this.onStateChange = null;    // callback for connection state changes
    this._reconnectTimer = null;
  }

  /**
   * Creates WebSocket connection and sets up event handlers
   */
  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => this._handleOpen();
      this.ws.onclose = (e) => this._handleClose(e);
      this.ws.onerror = (err) => this._handleError(err);
      this.ws.onmessage = (event) => this._handleMessage(event);
    } catch (err) {
      console.error('[WS] Connection error:', err);
      this._reconnect();
    }
  }

  /**
   * Close connection and stop auto-reconnect
   */
  disconnect() {
    this.autoReconnect = false;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    if (this.onStateChange) {
      this.onStateChange(false);
    }
  }

  /**
   * Send a command to the server
   * @param {string} cmd - Command name
   * @param {object} params - Command parameters
   */
  send(cmd, params) {
    if (!this.connected) {
      console.warn('[WS] Cannot send, not connected');
      return false;
    }
    const message = JSON.stringify({ cmd, params: params || {} });
    this.ws.send(message);
    return true;
  }

  /**
   * Register an event handler for a specific event type
   * Supports multiple handlers per event type
   * @param {string} eventType - Event type to listen for
   * @param {function} handler - Handler function
   */
  on(eventType, handler) {
    if (!this.handlers[eventType]) {
      this.handlers[eventType] = [];
    }
    this.handlers[eventType].push(handler);
  }

  /**
   * Remove an event handler
   * @param {string} eventType - Event type
   * @param {function} handler - Handler function to remove
   */
  off(eventType, handler) {
    if (!this.handlers[eventType]) return;
    this.handlers[eventType] = this.handlers[eventType].filter(h => h !== handler);
    if (this.handlers[eventType].length === 0) {
      delete this.handlers[eventType];
    }
  }

  /**
   * Parse incoming JSON message and dispatch to registered handlers
   */
  _handleMessage(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (err) {
      console.error('[WS] Failed to parse message:', err, event.data);
      return;
    }

    const eventType = data.type || data.event;
    if (!eventType) {
      console.warn('[WS] Message has no type/event field:', data);
      return;
    }

    const handlers = this.handlers[eventType];
    if (handlers && handlers.length > 0) {
      handlers.forEach(handler => {
        try {
          handler(data.data || data);
        } catch (err) {
          console.error(`[WS] Error in handler for "${eventType}":`, err);
        }
      });
    }

    // Also dispatch to wildcard handlers
    const wildcardHandlers = this.handlers['*'];
    if (wildcardHandlers && wildcardHandlers.length > 0) {
      wildcardHandlers.forEach(handler => {
        try {
          handler(eventType, data.data || data);
        } catch (err) {
          console.error('[WS] Error in wildcard handler:', err);
        }
      });
    }
  }

  /**
   * Handle successful connection
   */
  _handleOpen() {
    console.log('[WS] Connected to', this.url);
    this.reconnectAttempts = 0;
    if (this.onStateChange) {
      this.onStateChange(true);
    }
  }

  /**
   * Handle connection close, attempt reconnect with exponential backoff
   */
  _handleClose(event) {
    console.log('[WS] Connection closed:', event.code, event.reason);
    this.ws = null;
    if (this.onStateChange) {
      this.onStateChange(false);
    }
    if (this.autoReconnect) {
      this._reconnect();
    }
  }

  /**
   * Handle connection error
   */
  _handleError(err) {
    console.error('[WS] Error:', err);
  }

  /**
   * Schedule a reconnection with exponential backoff
   */
  _reconnect() {
    if (this._reconnectTimer) return;

    const delay = Math.min(
      this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts),
      this.maxReconnectDelay
    );
    this.reconnectAttempts++;

    console.log(`[WS] Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts})`);

    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.connect();
    }, delay);
  }

  /**
   * Check if currently connected
   * @returns {boolean}
   */
  get connected() {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}
