import { isAxiosError } from 'axios';
import { getMessageApi } from '@/utils/messageClient';

interface ApiErrorPayload {
  message?: string;
  detail?: string;
}

export const isAuthRequestError = (error: unknown): boolean => {
  return isAxiosError(error) && error.response?.status === 401;
};

export const getRequestErrorMessage = (error: unknown, fallback = 'Request failed'): string => {
  if (isAxiosError<ApiErrorPayload>(error)) {
    const data = error.response?.data;
    if (data?.message) return data.message;
    if (data?.detail) return data.detail;
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      return 'Request timed out. The server may still be processing; refresh the project list in a moment.';
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
};

export const showRequestError = (error: unknown, fallback = 'Request failed'): void => {
  if (isAuthRequestError(error)) return;

  const messageApi = getMessageApi();
  const message = getRequestErrorMessage(error, fallback);
  if (messageApi) {
    messageApi.error(message);
  } else {
    console.error(message);
  }
};
