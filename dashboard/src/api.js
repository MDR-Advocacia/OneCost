import axios from 'axios';

const API_URL = 'http://localhost:8001';

const api = axios.create({
  baseURL: API_URL,
});

// --- Funções da API ---

export const login = async (username, password) => {
    // O backend com OAuth2PasswordRequestForm espera dados de formulário, não JSON.
    const params = new URLSearchParams();
    params.append('username', username);
    params.append('password', password);

    const response = await api.post('/login', params, {
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    });
    return response;
};

export const checkLoginStatus = () => {
    // Simplesmente retorna uma promessa que resolve, já que o backend não está protegido ainda
    return Promise.resolve({ data: { username: 'admin' } });
};

