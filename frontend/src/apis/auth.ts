import service from '@/utils/https';

export interface UserProfile {
  id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  avatar?: string | null;
  gender?: string | null;
  is_active: boolean;
  is_verified: boolean;
  auth_provider: string;
  last_active_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user?: UserProfile;
}

interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export const login = (data: LoginRequest) => {
  return service.post<ApiResponse<LoginResponse>>('/v1/auth/login', data, {
    hideMessageModal: true,
  });
};

export const getCurrentUser = () => {
  return service.get<ApiResponse<UserProfile>>('/v1/users/me');
};
