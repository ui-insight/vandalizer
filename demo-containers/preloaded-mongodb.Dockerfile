# Step 1: Base image with MongoDB tools
FROM mongo:latest AS data-loader

# Set environment variable for DB name
ARG MONGODB_DB_NAME=osp

# Copy the dump into the container
COPY demo-data /demo-data

# Create data directory
RUN mkdir -p /data/db

# Start MongoDB in the background, restore the dump, then shut down
RUN mongod --dbpath /data/db --fork --logpath /var/log/mongod.log \
    && mongorestore --db "${MONGODB_DB_NAME}" /demo-data/osp-staging \
    && mongod --dbpath /data/db --shutdown

# Step 2: Final image with preloaded data
FROM mongo:latest

# Copy the preloaded data directory
COPY --from=data-loader /data/db /data/db

# Expose the default MongoDB port
EXPOSE 27017

# Start MongoDB with preloaded data
CMD ["mongod", "--dbpath", "/data/db", "--bind_ip_all"]