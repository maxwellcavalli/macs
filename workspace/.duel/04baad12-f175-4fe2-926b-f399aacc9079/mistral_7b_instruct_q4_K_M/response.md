To create a repository, service, and connect it to a controller to query users using R2DBC, follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, R2DBC, and any other necessary libraries.
2. Define your User entity class with the appropriate fields and annotations for mapping to a database table.
3. Create a repository interface that extends `R2dbcRepository` or `R2dbcEntityManagerRepository`. This will provide basic CRUD operations for your User entity.
4. Implement a service class that uses the repository to perform business logic related to user management, such as querying, updating, and deleting users.
5. Create a controller class that handles HTTP requests and responses. Use the service to interact with the database and return results to the client.
6. Configure your R2DBC connection by adding the appropriate properties to your `application.properties` or `application.yml` file.
7. Run your application and test your endpoints using a tool like Postman or curl.

Here's an example of how you might define your User entity class:
```java
@Entity
public class User {
    @Id
    private String id;
    private String name;
    private String email;

    // getters and setters
}
```
And here's an example of how you might define your repository interface:
```java
public interface UserRepository extends R2dbcEntityManagerRepository<User, String> {
}
```