# Estágio 1: Instalação das dependências
FROM node:18-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install

# Estágio 2: Construção e execução da aplicação
FROM node:18-alpine
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Expõe a porta que o React vai usar DENTRO do container
EXPOSE 3000

# Comando para iniciar o servidor
CMD ["npm", "start"]

