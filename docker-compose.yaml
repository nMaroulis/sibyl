version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    networks:
      - app_network

  frontend:
    build: ./frontend
    ports:
      - "8501:8501"
    depends_on:
      - backend
    networks:
      - app_network

networks:
  app_network:
    driver: bridge
