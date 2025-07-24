# Use a minimal base image (can be python, node, etc., depending on your app)
FROM alpine:latest

# Copy files from the local demo-data/files into the image
COPY demo-data/files/ /data/files

# Default command (replace with your app’s start command if needed)
CMD ["cp", "-r", "/srv/files/*", "/app/app/static/uploads/"]