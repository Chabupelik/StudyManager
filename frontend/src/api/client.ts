import { appBridge } from '../utils/bridge';

export interface ApiOptions {
  method?: string;
  body?: any;
  headers?: Record<string, string>;
}

export class ApiClient {
  public static async request<T = any>(url: string, options: ApiOptions = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers || {}),
    };

    const authHeaders = appBridge.getAuthHeaders();
    Object.assign(headers, authHeaders);

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
