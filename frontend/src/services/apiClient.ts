const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(/\/$/, '');

interface ApiErrorBody {
  detail?: string;
}

function buildUrl(path: string) {
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

async function parseResponse(response: Response) {
  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    return response.json();
  }

  return response.text();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildUrl(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  const payload = await parseResponse(response);

  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in (payload as ApiErrorBody)
        ? (payload as ApiErrorBody).detail
        : undefined;

    throw new Error(detail || '요청 처리 중 오류가 발생했습니다.');
  }

  return payload as T;
}

export const apiClient = {
  get<T>(path: string) {
    return request<T>(path, {
      method: 'GET',
    });
  },
  post<T>(path: string, body?: unknown) {
    return request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
};
