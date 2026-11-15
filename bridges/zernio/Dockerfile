FROM node:20-alpine

WORKDIR /app
COPY --chown=node:node package.json ./
COPY --chown=node:node src ./src
COPY --chown=node:node data ./data
USER node

ENV NODE_ENV=production
CMD ["node", "src/server.js"]
