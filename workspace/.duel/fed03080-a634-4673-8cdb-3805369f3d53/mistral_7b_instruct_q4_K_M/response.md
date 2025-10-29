To create a repository, service, and connect it to a controller to query users using R2DBC, follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, R2DBC, and any other necessary libraries.
2. Define your User entity class with the appropriate fields and annotations for mapping to a database table.
3. Create a repository interface that extends `R2dbcRepository` or `R2dbcQueryable`. This will provide basic CRUD operations for your User entity.
4. Implement a service class that uses the repository to perform business logic related to user management, such as querying, updating, and deleting users.
5. Create a controller class that handles HTTP requests and calls the appropriate methods in the service class to perform actions on users.
6. Configure your database connection details in the application properties or application.yml file.
7. Run your Spring Boot application and test your API endpoints using a tool like Postman or curl.

Here's an example of how your User entity class might look:
```java
@Entity
public class User {
    @Id
    private String id;
    private String name;
    private String email;

    // Getters and setters
}
```
And here's an example of how your repository interface might look:
```java
public interface UserRepository extends R2dbcQueryable<User> {
    User findById(String id);
    List<User> findAll();
    User save(User user);
}
```