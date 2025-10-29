To create a repository, service, and connect it to a controller to query users using R2DBC, you can follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, R2DBC, and your preferred database driver (e.g., PostgreSQL or MySQL).
```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>io.r2dbc</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <version>0.8.3</version>
    </dependency>
</dependencies>
```
1. Create a new repository interface that extends `R2dbcRepository`. This will allow you to query your database using R2DBC.
```java
public interface UserRepository extends R2dbcRepository<User, Long> {
}
```
1. Create a new service class that will handle the business logic for querying users. Inject the `UserRepository` into this class and implement methods to query users based on your requirements.
```java
@Service
public class UserService {

    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public List<User> findAll() {
        return userRepository.findAll();
    }

    // Implement other methods for querying users based on your requirements
}
```
1. Create a new controller class that will handle incoming HTTP requests and delegate the processing to the `UserService`. Inject the `UserService` into this class and define methods to map HTTP endpoints to service methods.
```java
@RestController
@RequestMapping("/api/users")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping
    public List<User> getAllUsers() {
        return userService.findAll();
    }

    // Define other methods for mapping HTTP endpoints to service methods
}
```
That's it! You now have a repository, service, and controller set up to query users using R2DBC in your Spring Boot application.