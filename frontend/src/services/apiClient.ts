interface ApiErrorBody {
  detail?: string;
}

function getApiBaseUrl() {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

  if (!apiBaseUrl) {
    throw new Error('API 주소가 설정되지 않았습니다. frontend/.env의 VITE_API_BASE_URL을 확인해주세요.');
  }

  return apiBaseUrl.replace(/\/$/, '');
}

function buildUrl(path: string) {
  return `${getApiBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`;
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
