# Stage 1: Build the application
FROM node:20-alpine as build

# Set environment variables
# Because Vite is used, we can't pass the variables directly to the build command
# So we need to create a .env.production file with our variables
ARG VITE_API_BASE_URL
RUN echo "VITE_API_BASE_URL=$VITE_API_BASE_URL" > .env.production

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy all files
COPY . .

# Build the app
RUN npm run build

# Stage 2: Serve the application
FROM nginx:alpine

# Copy the built app to nginx's serve directory
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create .htaccess file to ensure proper MIME types
RUN echo "AddType application/javascript .js .mjs" > /usr/share/nginx/html/.htaccess

# Expose port 80
EXPOSE 80

# Command to run when container starts
CMD ["nginx", "-g", "daemon off;"]
