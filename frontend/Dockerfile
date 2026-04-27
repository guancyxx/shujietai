FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci || npm install

COPY . .

CMD ["npm", "run", "dev"]
