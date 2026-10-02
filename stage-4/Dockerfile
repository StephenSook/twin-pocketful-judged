FROM node:24-slim
ENV NODE_ENV=production PORT=8080
WORKDIR /app
COPY package.json ./
COPY src ./src
COPY public ./public
USER node
EXPOSE 8080
CMD ["node", "src/server.js"]
