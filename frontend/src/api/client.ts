import { appBridge } from '../utils/bridge';

export interface ApiOptions {
  method?: string;
  body?: any;
  headers?: Record<string, string>;
}

export class ApiClient {
  private static token: string | null = localStorage.getItem('study_jwt_token');

  public static setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('study_jwt_token', token);
    } else {
      localStorage.removeItem('study_jwt_token');
    }
  }

  public static getToken(): string | null {
    return this.token;
  }

  public static async request<T = any>(url: string, options: ApiOptions = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers || {}),
    };

    // Auth header: X-Telegram-Init-Data (TG) или X-VK-Sign (VK)
    const authHeaders = appBridge.getAuthHeaders();
    Object.assign(headers, authHeaders);

    // JWT Bearer для PC-входа

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    let body: BodyInit | undefined = undefined;

    if (options.body) {
      if (options.body instanceof FormData) {
        body = options.body;
      } else {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(options.body);
      }
    }

    const res = await fetch(url, {
      method: options.method || 'GET',
      headers,
      body,
    });

    if (res.status === 401) {
      throw new Error('UNAUTHORIZED');
    }

    if (res.status === 403) {
      const err = await res.json().catch(() => ({}));
      if (err.detail === 'NOT_IN_GROUP') {
        throw new Error('FORBIDDEN_NOT_IN_GROUP');
      }
      throw new Error('FORBIDDEN');
    }

    if (res.status === 429) {
      throw new Error('LIMIT_EXCEEDED');
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    // Return JSON or empty object
    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return res.json();
    }
    return {} as T;
  }

  public static get<T = any>(url: string, headers?: Record<string, string>): Promise<T> {
    return this.request<T>(url, { method: 'GET', headers });
  }

  public static post<T = any>(url: string, body?: any, headers?: Record<string, string>): Promise<T> {
    return this.request<T>(url, { method: 'POST', body, headers });
  }

  public static put<T = any>(url: string, body?: any, headers?: Record<string, string>): Promise<T> {
    return this.request<T>(url, { method: 'PUT', body, headers });
  }

  public static delete<T = any>(url: string, headers?: Record<string, string>): Promise<T> {
    return this.request<T>(url, { method: 'DELETE', headers });
  }
}
