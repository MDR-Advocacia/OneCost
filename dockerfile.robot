FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Instala o Xvfb (Monitor Virtual) e o utilitário dos2unix para prevenir erros de quebra de linha do Windows
RUN apt-get update && apt-get install -y xvfb dos2unix && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./robot ./robot
COPY robot_entrypoint.sh /app/robot_entrypoint.sh

# Corrige possíveis quebras de linha do Windows (CRLF) para Linux (LF) e dá permissão de execução
RUN dos2unix /app/robot_entrypoint.sh && chmod +x /app/robot_entrypoint.sh

ENV PYTHONPATH=/app/robot
ENV PYTHONUNBUFFERED=1

# O PULO DO GATO: Usa o script como inicializador
CMD ["/app/robot_entrypoint.sh"]