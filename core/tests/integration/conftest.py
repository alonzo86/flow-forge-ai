def create_postgres_handler():
    from testcontainers.postgres import PostgresContainer
    from flow_forge_ai.sinks.handlers.postgres_handler import PostgresHandler


    with PostgresContainer("postgres:17") as container:
        yield PostgresHandler(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(5432)),
            database=container.dbname,
            user=container.username,
            password=container.password,
        )


def create_mysql_handler():
    from testcontainers.mysql import MySqlContainer
    from flow_forge_ai.sinks.handlers.mysql_handler import MySQLHandler

    with MySqlContainer("mysql:8.0") as container:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(3306))

        yield MySQLHandler(
            host=host,
            port=port,
            database=container.dbname,
            user=container.username,
            password=container.password,
        )


def create_mongo_handler():
    from testcontainers.mongodb import MongoDbContainer
    from flow_forge_ai.sinks.handlers.mongodb_handler import MongoDBHandler

    with MongoDbContainer("mongo:7") as container:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(27017))

        # Mongo URI is usually simplest here
        uri = container.get_connection_url()

        yield MongoDBHandler(
            uri=uri,
            database="test",
        )
