To create a repository, service, and connect it to a controller to query users using R2DBC in Spring Boot, follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, R2DBC, and any other necessary libraries.
2. Define your User entity class with appropriate annotations for mapping to the database schema.
3. Create a repository interface that extends `R2dbcRepository` and defines methods for querying users.
4. Implement the repository interface using Spring Data R2DBC's reactive programming model.
5. Create a service class that uses the repository to perform business logic related to user queries.
6. Create a controller class that exposes REST endpoints for querying users and handles incoming requests.
7. Configure your database connection details in `application.properties` or `application.yml`.
8. Run your application and test the user query functionality using a tool like Postman or curl.

Here's an example of how you might implement the repository interface:
```java
import org.springframework.data.r2dbc.repository.R2dbcRepository;
import reactor.core.publisher.Flux;

public interface UserRepository extends R2dbcRepository<User, Long> {
    Flux<User> findAll();
}
```
And here's an example of how you might implement the service class:
```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class UserService {
    @Autowired
    private UserRepository userRepository;

    public Flux<User> getAllUsers() {
        return userRepository.findAll();
    }
}
```
Please let me know if you need more detailed code examples or have any specific questions about this process.