To create a repository, service, and connect it to a controller to query users using R2DBC, you can follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, R2DBC, and any other necessary libraries.
2. Define your User entity in the `User.java` file with the appropriate fields and annotations.
3. Create a repository interface that extends `R2dbcRepository` and define methods for querying users. For example:
```typescript
public interface UserRepository extends R2dbcRepository<User, Long> {
    List<User> findAll();
    Optional<User> findById(Long id);
}
```
1. Create a service class that will handle the business logic for querying users. This class should use the repository to perform database operations and return the results to the controller. For example:
```typescript
@Service
public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public List<User> findAll() {
        return userRepository.findAll();
    }

    public Optional<User> findById(Long id) {
        return userRepository.findById(id);
    }
}
```
1. Create a controller class that will handle incoming HTTP requests and delegate the querying of users to the service. For example:
```typescript
@RestController
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/users")
    public List<User> getAllUsers() {
        return userService.findAll();
    }

    @GetMapping("/users/{id}")
    public Optional<User> getUserById(@PathVariable Long id) {
        return userService.findById(id);
    }
}
```
1. Configure your database connection in the `application.properties` file or using an environment variable. For example:
```makefile
spring.datasource.url=jdbc:postgresql://localhost:5432/mydatabase
spring.datasource.username=myuser
spring.datasource.password=mypassword
spring.r2dbc.driverClassName=org.postgresql.Driver
spring.r2dbc.url=jdbc:postgresql://localhost:5432/mydatabase
spring.r2dbc.username=myuser
spring.r2dbc.password=mypassword
```
That's it! You now have a repository, service, and controller set up to query users using R2DBC in Spring Boot.