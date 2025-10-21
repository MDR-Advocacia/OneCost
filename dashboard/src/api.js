import axios from 'axios';

const API_URL = 'http://localhost:8001'; // A porta do seu backend

const api = axios.create({
  baseURL: API_URL,
});

// Interceptor para adicionar o token de autenticação em todas as requisições
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// --- FUNÇÕES DA API ---

export const login = async (username, password) => {
  // O backend com OAuth2PasswordRequestForm espera dados de formulário
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);

  const response = await api.post('/login', params, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });
  // Salva o token no localStorage após o login
  if (response.data.access_token) {
    localStorage.setItem('token', response.data.access_token);
  }
  return response.data;
};

export const getCurrentUser = async () => {
    const response = await api.get('/users/me');
    return response.data;
};

export const getSolicitacoes = async () => {
    const response = await api.get('/solicitacoes/');
    return response.data;
};

export const createSolicitacao = async (solicitacaoData) => {
    const response = await api.post('/solicitacoes/', solicitacaoData);
    return response.data;
};
