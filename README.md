# 🤖 OneCost

O **OneCost** é um projeto de Automação de Processos Robóticos (RPA) desenvolvido com o objetivo de otimizar a consulta e extração de informações sobre custas judiciais.

Este robô faz parte da família de sistemas **One**, um ecossistema de soluções internas já consolidado e em pleno funcionamento.

## 🎯 Objetivo

O objetivo principal do `OneCost` é automatizar o processo de levantamento de custas judiciais solicitadas a um de nossos clientes, garantindo agilidade, precisão e rastreabilidade das informações.

## 🛠️ Tecnologias Utilizadas

* **Python**: Linguagem principal do projeto.
* **Playwright**: Biblioteca de automação web utilizada para a interação com os portais e sistemas necessários.

## Variáveis de Ambiente

O arquivo `.env` já está ignorado no Git. Para configurar o projeto em ambientes como Coolify/AWS, use o arquivo `.env.example` como referência.

Principais variáveis do backend:

* `DATABASE_URL`
* `POSTGRES_HOST`
* `POSTGRES_PORT`
* `POSTGRES_USER`
* `SECRET_KEY`
* `ADMIN_USERNAME`
* `ADMIN_PASSWORD`
* `AD_SERVER_IP`
* `AD_DOMAIN`
* `AD_BASE_DN`
* `AD_SERVICE_USER`
* `AD_SERVICE_PASS`

Compatibilidade com o ecossistema One:

* Se `AD_SERVICE_USER` e `AD_SERVICE_PASS` não forem definidos, o backend usa fallback para `ONELOG_USERNAME` e `ONELOG_PASSWORD`.

Frontend:

* `REACT_APP_API_URL=https://onecost.mdradvocacia.com`
