import axios from 'axios';

// ---> MUDANÇA: Exportar API_URL para o App.js usar <---
export const API_URL = 'http://localhost:8001'; // A porta do seu backend

const api = axios.create({
  baseURL: API_URL,
});

// Interceptor para adicionar o token de autenticação em todas as requisições
api.interceptors.request.use(
  (config) => {
// ... (resto do arquivo api.js sem alterações) ...
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    console.error("Erro no interceptor de requisição:", error);
    return Promise.reject(error);
  }
);

// Interceptor de Resposta: Trata erros globais, como token expirado (401)
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error("Erro na resposta da API:", error.response || error.message);
    if (error.response && error.response.status === 401) {
      console.warn("Recebido erro 401. Token inválido ou expirado. Removendo token.");
      localStorage.removeItem('token');
      window.location.reload(); 
    }
    return Promise.reject(error);
  }
);


// --- FUNÇÕES DE AUTENTICAÇÃO ---

export const login = async (username, password) => {
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);

  console.log("Enviando para /login com:", { username });
  const response = await api.post('/login', params, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });

  if (response.data.access_token) {
    console.log("Login bem-sucedido. Token recebido:", response.data.access_token.substring(0, 10) + "...");
    localStorage.setItem('token', response.data.access_token);
  } else {
    console.warn("Resposta de login OK, mas sem access_token.");
  }
  return response.data;
};

export const getCurrentUser = async () => {
    console.log("Buscando dados do usuário atual (/users/me)...");
    const response = await api.get('/users/me');
    console.log("Dados do usuário:", response.data);
    return response.data;
};


// --- FUNÇÕES DE SOLICITAÇÕES DE CUSTAS (CRUD) ---

export const getSolicitacoes = async () => {
    console.log("Buscando lista de solicitações (/solicitacoes)...");
    const response = await api.get('/solicitacoes/');
    console.log(`Recebidas ${response.data.length} solicitações.`);
    return response.data;
};

export const createSolicitacao = async (solicitacaoData) => {
    console.log("Enviando nova solicitação para /solicitacoes:", solicitacaoData);
    const response = await api.post('/solicitacoes/', solicitacaoData);
    console.log("Solicitação criada com sucesso:", response.data);
    return response.data;
};

export const updateSolicitacao = async (id, solicitacaoData) => {
    console.log(`Enviando atualização para ID ${id}:`, solicitacaoData);
    const response = await api.put(`/solicitacoes/${id}`, solicitacaoData);
    console.log("Atualização bem-sucedida:", response.data);
    return response.data;
};

// Exporta a instância do axios caso precise usá-la diretamente
export default api;

