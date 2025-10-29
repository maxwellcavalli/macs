To create a repository, service, and connect it to a controller to query users using R2DBC in Spring Boot, follow these steps:

1. Create a new Spring Boot project with the following dependencies:
```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```
1. Create a new repository interface that extends `R2dbcRepository`. For example:
```java
public interface UserRepository extends R2dbcRepository<User, Long> {
}
```
1. Create a new service class that will handle the business logic for querying users. For example:
```java
@Service
public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public List<User> getAllUsers() {
        return userRepository.findAll();
    }
}
```
1. Create a new controller class that will handle incoming HTTP requests and delegate the querying of users to the service. For example:
```java
@RestController
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/users")
    public List<User> getAllUsers() {
        return userService.getAllUsers();
    }
}
```
1. Configure your R2DBC connection by adding the following properties to your `application.properties` file:
```properties
spring.data.r2dbc.uri=jdbc:postgresql://localhost:5432/mydatabase
spring.data.r2dbc.username=myuser
spring.data.r2dbc.password=mypassword
```
Replace `mydatabase`, `myuser`, and `mypassword` with your actual database name, username, and password.

That's it! You now have a repository, service, and controller set up to query users using R2DBC in Spring Boot.