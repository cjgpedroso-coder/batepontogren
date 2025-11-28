FROM python:3.11-slim

# Diretório de trabalho
WORKDIR /app

# Copia requisitos e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código
COPY . .

# Garante que a pasta de dados exista
RUN mkdir -p data

# Comando para iniciar o bot
CMD ["python", "bot.py"]
