FROM node:20-alpine

WORKDIR /app/frontend

ARG BACKEND_URL=http://backend:8000
ARG NEXT_PUBLIC_CHAT_WS_URL=ws://localhost:8000/api/chat/ws

ENV BACKEND_URL=${BACKEND_URL}
ENV NEXT_PUBLIC_CHAT_WS_URL=${NEXT_PUBLIC_CHAT_WS_URL}

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
