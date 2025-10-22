import axios from 'axios';

// Define a URL base da sua API backend
// Certifique-se que esta URL está acessível a partir de onde o frontend está rodando
// Se backend e frontend rodam via docker-compose na mesma máquina, localhost geralmente funciona.
const API_URL = 'http://localhost:8001'; // Usando a porta do backend definida no docker-compose

// Cria uma instância do axios com a URL base
const api = axios.create({
  baseURL: API_URL,
});

// Interceptor: Adiciona o token JWT ao cabeçalho Authorization de cada requisição
// se um token estiver armazenado no localStorage.
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      // O formato padrão é 'Bearer SEU_TOKEN'
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    // Faz algo com o erro da requisição
    console.error("Erro no interceptor de requisição:", error);
    return Promise.reject(error);
  }
);

// Interceptor de Resposta: Trata erros globais, como token expirado (401)
api.interceptors.response.use(
  (response) => {
    // Qualquer status code que caia dentro do range de 2xx causa essa função ser disparada
    return response;
  },
  (error) => {
    // Qualquer status code fora do range de 2xx causa essa função ser disparada
    console.error("Erro na resposta da API:", error.response || error.message);
    if (error.response && error.response.status === 401) {
      // Se receber 401 Unauthorized (token inválido/expirado),
      // remove o token antigo e força o reload para ir para a tela de login.
      console.warn("Recebido erro 401. Token inválido ou expirado. Removendo token.");
      localStorage.removeItem('token');
      // Recarrega a página para forçar a ida para a tela de login no App.js
      // window.location.reload();
      // Ou, se estiver usando React Router, redirecionar para /login
    }
    // Retorna a promessa rejeitada para que o erro possa ser tratado no local da chamada (catch)
    return Promise.reject(error);
  }
);


// --- FUNÇÕES DE AUTENTICAÇÃO ---

/**
 * Envia as credenciais para a API para obter um token de acesso.
 * @param {string} username - O nome de usuário.
 * @param {string} password - A senha.
 * @returns {Promise<object>} A resposta da API contendo o token.
 */
export const login = async (username, password) => {
  // O endpoint /login do FastAPI com OAuth2PasswordRequestForm espera
  // os dados como 'form data' (application/x-www-form-urlencoded).
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);

  console.log("Enviando para /login com:", { username }); // Não logar senha
  const response = await api.post('/login', params, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });

  // Se o login foi bem-sucedido e recebemos um token, armazena no localStorage.
  if (response.data.access_token) {
    console.log("Login bem-sucedido. Token recebido:", response.data.access_token.substring(0, 10) + "..."); // Mostra só o início do token
    localStorage.setItem('token', response.data.access_token);
  } else {
    console.warn("Resposta de login OK, mas sem access_token.");
  }
  return response.data; // Retorna a resposta completa ({access_token: "...", token_type: "bearer"})
};

/**
 * Busca os dados do usuário atualmente logado usando o token armazenado.
 * @returns {Promise<object>} Os dados do usuário.
 */
export const getCurrentUser = async () => {
    console.log("Buscando dados do usuário atual (/users/me)...");
    const response = await api.get('/users/me');
    console.log("Dados do usuário:", response.data);
    return response.data; // Retorna {id: ..., username: ...}
};


// --- FUNÇÕES DE SOLICITAÇÕES DE CUSTAS ---

/**
 * Busca a lista de solicitações de custas da API.
 * @returns {Promise<Array<object>>} Uma lista de objetos de solicitação.
 */
export const getSolicitacoes = async () => {
    console.log("Buscando lista de solicitações (/solicitacoes)...");
    const response = await api.get('/solicitacoes/');
    console.log(`Recebidas ${response.data.length} solicitações.`);
    return response.data; // Retorna um array de solicitações
};

/**
 * Cria uma nova solicitação de custa na API.
 * @param {object} solicitacaoData - Os dados da nova solicitação.
 * @returns {Promise<object>} O objeto da solicitação criada.
 */
export const createSolicitacao = async (solicitacaoData) => {
    console.log("Enviando nova solicitação para /solicitacoes:", solicitacaoData);
    const response = await api.post('/solicitacoes/', solicitacaoData);
    console.log("Solicitação criada com sucesso:", response.data);
    return response.data; // Retorna a solicitação criada com ID
};

// Adicionar aqui outras funções da API conforme necessário (ex: updateSolicitacao, deleteSolicitacao)

// Exporta a instância do axios caso precise usá-la diretamente em algum lugar
export default api;
