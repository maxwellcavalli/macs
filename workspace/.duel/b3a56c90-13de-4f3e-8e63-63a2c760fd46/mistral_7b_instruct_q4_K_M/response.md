To create a repository, service, and connect it to a controller to query users using R2DBC in Spring Boot, follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, R2DBC, and any other required libraries.
2. Define your User entity class with the necessary fields and annotations for JPA to map it to a database table.
3. Create a repository interface that extends `R2dbcRepository` or one of its subclasses, such as `R2dbcJpaRepository`. This will provide basic CRUD operations for your User entity.
4. Implement the repository interface with any custom methods or logic needed for querying users.
5. Create a service class that uses the repository to perform business logic and interact with the database.
6. Create a controller class that handles HTTP requests and invokes the appropriate methods in the service layer.
7. Configure your R2DBC connection details, such as the URL, username, password, and driver, in the application properties or configuration file.
8. Run your Spring Boot application and test your endpoints using a tool like Postman or curl.

Here's an example of how your User entity class might look:
```java
@Entity
public class User {
    @Id
    private Long id;
    private String name;
    private String email;

    // Getters and setters
}
```
And here's an example of how your repository interface might look:
```java
public interface UserRepository extends R2dbcJpaRepository<User, Long> {
    List<User> findByName(String name);
}
```
Please let me know if you need more detailed code snippets or have any specific questions.