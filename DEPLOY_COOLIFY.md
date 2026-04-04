# Deploy no Coolify

Este guia parte do zero e considera:

- codigo local ainda nao commitado
- base atual rodando no Docker Desktop em um PC Windows
- futuro deploy em Coolify/AWS
- dominio final: `https://onecost.mdradvocacia.com`

## 1. Preparar o repositorio

Antes de qualquer deploy no Coolify, o codigo precisa estar em um repositorio Git remoto.

Fluxo sugerido:

```bash
git status
git add .
git commit -m "prep: deploy onecost no coolify"
git remote add origin <URL_DO_REPOSITORIO>
git push -u origin <SUA_BRANCH>
```

Se o repositório remoto ja existir:

```bash
git remote -v
git push origin <SUA_BRANCH>
```

## 2. Gerar dump do banco atual no Windows

No computador Windows onde a branch `Windows` esta rodando hoje:

### Opcao A: dump SQL simples

No PowerShell:

```powershell
docker exec -t onecost_db pg_dump -U admin -d onecost > onecost_producao.sql
```

### Opcao B: dump em formato custom

```powershell
docker exec -t onecost_db pg_dump -U admin -d onecost -Fc > onecost_producao.dump
```

Se nao tiver certeza do nome do container:

```powershell
docker ps
```

Recomendacao:

- gere `onecost_producao.sql`
- gere tambem `onecost_producao.dump`

## 3. Estrategia de deploy no Coolify

Use o arquivo:

- `docker-compose.coolify.yml`

Ele sobe:

- `db`
- `backend`
- `dashboard`
- `robot`

Observacao:

- a dashboard no Coolify usa build estatico + `nginx`, nao `npm start`
- isso reduz bastante o consumo de memoria em comparacao com o servidor de desenvolvimento do React

## 4. Criar o projeto no Coolify

No Coolify:

1. Crie um novo projeto.
2. Escolha `Docker Compose`.
3. Aponte para o repositório Git.
4. Selecione o arquivo `docker-compose.coolify.yml`.
5. Garanta que o `build arg` `REACT_APP_API_URL` esteja preenchido via variavel do ambiente do stack, porque o React consome isso no build da imagem.

## 5. Variaveis de ambiente no Coolify

Cadastre estas variaveis no stack/app do Coolify.

### Banco

```env
POSTGRES_DB=onecost
POSTGRES_USER=admin
POSTGRES_PASSWORD=<senha-forte>
DATABASE_URL=postgresql://admin:<senha-forte>@db:5432/onecost
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

### Backend

```env
SECRET_KEY=<chave-forte>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<senha-admin-forte>
```

### AD

```env
AD_SERVER_IP=<ip-do-ad>
AD_DOMAIN=mdr.local
AD_BASE_DN=DC=mdr,DC=local
AD_SERVICE_USER=robo.onecost
AD_SERVICE_PASS=<senha-do-servico>
```

Observacao:

- o backend usa fallback para `ONELOG_USERNAME` e `ONELOG_PASSWORD`
- mas em producao prefira definir `AD_SERVICE_USER` e `AD_SERVICE_PASS` explicitamente

### Compatibilidade com OneLog

```env
ONELOG_USERNAME=robo.onecost
ONELOG_PASSWORD=<senha-do-servico>
ONELOG_API_URL=https://api-onelog.mdradvocacia.com
```

### Dashboard

```env
REACT_APP_API_URL=https://onecost.mdradvocacia.com
```

### Robo

```env
ROBOT_USERNAME=robot
ROBOT_PASSWORD=<senha-do-robo>
API_BASE_URL=http://backend:8000
URL_PORTAL_CUSTAS=https://juridico.bb.com.br/paj/app/paj-custos/spas/custos/custos.app.html#/inicio/*
DOWNLOAD_TIMEOUT_MS=60000
SESSION_TIMEOUT_SECONDS=1800
```

## 6. Rede e dominio

No Coolify:

1. publique o `backend`
2. publique a `dashboard`
3. aponte o dominio final para a dashboard: `onecost.mdradvocacia.com`

Observacao importante:

- hoje o frontend chama a API pela variavel `REACT_APP_API_URL`
- entao o backend precisa estar acessivel por HTTPS tambem

## 7. Restaurar o banco no ambiente novo

Depois que o stack subir e o PostgreSQL estiver de pe:

### Se usar dump SQL

Entre no container do banco ou use terminal do serviço:

```bash
psql "postgresql://admin:<senha-forte>@db:5432/onecost" < onecost_producao.sql
```

### Se usar dump custom

```bash
pg_restore --no-owner --no-privileges -d "postgresql://admin:<senha-forte>@db:5432/onecost" onecost_producao.dump
```

Se o restore for feito fora do container, substitua `db` pelo host acessivel no ambiente.

## 8. Depois do restore

O backend ja esta preparado para:

- criar colunas novas se faltarem
- garantir usuario admin local
- garantir usuario robot local
- autenticar usuarios no AD
- sincronizar setor no login

## 9. Validacoes finais

Depois do deploy:

1. testar login com admin local
2. testar login com usuario AD
3. confirmar se o setor foi preenchido no usuario
4. confirmar filtros:
   - usuario comum: `Minhas Solicitações`
   - usuario comum: `Meu Setor`
   - admin: `Todas`
5. testar criacao de solicitacao
6. testar robo e acesso ao OneLog

## 10. Conectividade AWS -> AD

Sem isso o login AD nao funciona.

Voce precisa garantir:

- saida da instancia/servidor para o AD
- porta `636` liberada para LDAPS
- rota/VPN/peering se o AD estiver em rede privada
- certificado do AD aceito
