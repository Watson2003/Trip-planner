export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
}

export interface LoginForm {
  email: string;
  password: string;
}

export interface RegisterForm {
  username: string;
  email: string;
  password: string;
  full_name: string;
  confirmPassword: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}
