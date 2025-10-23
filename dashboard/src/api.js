import axios from 'axios';

// URL base da API do backend
export const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8001';

const api = axios.create({
  baseURL: API_URL,
});

// Interceptor para adicionar o token de autenticação
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Adiciona Content-Type se não for login
    if (!config.url.endsWith('/login')) {
         // Default para JSON se não especificado
        if (!config.headers['Content-Type']) {
            config.headers['Content-Type'] = 'application/json';
        }
    }
    return config;
  },
  (error) => {
    console.error("Erro no interceptor de requisição:", error);
    return Promise.reject(error);
  }
);

// Interceptor de Resposta: Trata erros 401 (token expirado/inválido)
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error("Erro na resposta da API:", error.response?.status, error.response?.data || error.message);
    if (error.response && error.response.status === 401) {
      console.warn("Recebido erro 401. Token inválido ou expirado. Removendo token e recarregando.");
      localStorage.removeItem('token');
      // Força recarregamento para redirecionar para login
      if (window.location.pathname !== '/login') { // Evita loop se já estiver no login
           window.location.href = '/login?sessionExpired=true'; // Ou apenas reload()
      }
    }
    // Rejeita a promessa com o erro original para tratamento local
    return Promise.reject(error);
  }
);


// --- FUNÇÕES DE AUTENTICAÇÃO ---

export const login = async (username, password) => {
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);

  console.log("[api.js] Enviando para /login com:", { username });
  // Sobrescreve Content-Type especificamente para login
  const response = await api.post('/login', params, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });

  if (response.data.access_token) {
    console.log("[api.js] Login bem-sucedido. Token recebido.");
    localStorage.setItem('token', response.data.access_token);
  } else {
    console.warn("[api.js] Resposta de login OK, mas sem access_token.");
  }
  return response.data; // Retorna { access_token, token_type }
};

export const getCurrentUser = async () => {
    console.log("[api.js] Buscando dados do usuário atual (/users/me)...");
    const response = await api.get('/users/me');
    console.log("[api.js] Dados do usuário:", response.data);
    return response.data; // Retorna { id, username, role, is_active }
};


// --- FUNÇÕES DE SOLICITAÇÕES DE CUSTAS (CRUD + Ações) ---

// Modificado para aceitar include_archived
export const getSolicitacoes = async (includeArchived = false) => {
    console.log(`[api.js] Buscando lista de solicitações (/solicitacoes)... includeArchived=${includeArchived}`);
    const params = { include_archived: includeArchived };
    const response = await api.get('/solicitacoes/', { params });
    console.log(`[api.js] Recebidas ${response.data.length} solicitações.`);
    return response.data;
};

export const createSolicitacao = async (solicitacaoData) => {
    console.log("[api.js] Enviando nova solicitação para /solicitacoes:", solicitacaoData);
    const response = await api.post('/solicitacoes/', solicitacaoData);
    console.log("[api.js] Solicitação criada com sucesso:", response.data);
    return response.data;
};

// Usado para resetar para pendente, marcar como finalizado, etc.
export const updateSolicitacao = async (id, solicitacaoData) => {
    console.log(`[api.js] Enviando atualização PUT para /solicitacoes/${id}:`, solicitacaoData);
    const response = await api.put(`/solicitacoes/${id}`, solicitacaoData);
    console.log("[api.js] Atualização de solicitação bem-sucedida:", response.data);
    return response.data;
};

// NOVO: Arquivar/Desarquivar Solicitação (Admin)
export const archiveSolicitation = async (id, isArchived) => {
    console.log(`[api.js] Enviando pedido de arquivamento PUT para /solicitacoes/${id}/archive:`, { is_archived: isArchived });
    // O backend espera { "is_archived": true/false } no corpo
    const response = await api.put(`/solicitacoes/${id}/archive`, { is_archived: isArchived });
    console.log("[api.js] Arquivamento/Desarquivamento bem-sucedido:", response.data);
    return response.data;
}

// NOVO: Resetar Erros (Admin)
export const resetarErrosSolicitacoes = async () => {
    console.log("[api.js] Enviando POST para /solicitacoes/resetar-erros");
    const response = await api.post('/solicitacoes/resetar-erros');
    console.log("[api.js] Resposta do reset de erros:", response.data);
    return response.data; // Retorna { message: "X solicitações..." }
}


// --- FUNÇÕES DE GERENCIAMENTO DE USUÁRIOS (Admin) ---

// NOVO: Criar Usuário (Admin)
export const createUser = async (userData) => {
    console.log("[api.js] Enviando POST para /users/ (criar usuário):", { username: userData.username, role: userData.role });
    const response = await api.post('/users/', userData);
    console.log("[api.js] Usuário criado com sucesso:", response.data);
    return response.data;
};

// NOVO: Listar Usuários (Admin)
export const listUsers = async () => {
    console.log("[api.js] Buscando GET /users/ (lista de usuários)...");
    const response = await api.get('/users/');
    console.log(`[api.js] Recebidos ${response.data.length} usuários.`);
    return response.data;
};

// NOVO: Atualizar Status do Usuário (Ativar/Desativar) (Admin)
export const updateUserStatus = async (userId, isActive) => {
    console.log(`[api.js] Enviando PUT para /users/${userId}/status:`, { is_active: isActive });
    const response = await api.put(`/users/${userId}/status`, { is_active: isActive });
    console.log("[api.js] Status do usuário atualizado:", response.data);
    return response.data;
};


// Exporta a instância do axios caso precise usá-la diretamente (raro)
export default api;
