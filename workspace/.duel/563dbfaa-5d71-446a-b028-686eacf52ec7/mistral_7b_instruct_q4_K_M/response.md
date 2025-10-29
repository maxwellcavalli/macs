To create a repository, service, and connect it to a controller to query users using R2DBC in Spring Boot, follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, R2DBC, and any other required libraries.
2. Define your User entity class with the necessary fields and annotations.
3. Create a repository interface that extends `R2dbcRepository` and define methods for CRUD operations on the User entity.
4. Implement a service class that uses the repository to perform business logic and interact with the database.
5. Create a controller class that handles HTTP requests and invokes the service methods to query users.
6. Configure your R2DBC connection properties in the `application.properties` file or using environment variables.
7. Run your application and test the endpoints to query users.

Here's an example of how you can implement a repository interface for querying users:
```java
public interface UserRepository extends R2dbcRepository<User, Long> {
    List<User> findAll();
    Optional<User> findById(Long id);
    User save(User user);
    void deleteById(Long id);
}
```
And here's an example of how you can implement a service class that uses the repository to query users:
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

    public Optional<User> getUserById(Long id) {
        return userRepository.findById(id);
    }

    public User createUser(User user) {
        return userRepository.save(user);
    }

    public void deleteUser(Long id) {
        userRepository.deleteById(id);
    }
}
```
And here's an example of how you can implement a controller class that handles HTTP requests and invokes the service methods:
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
        return userService.getAllUsers();
    }

    @GetMapping("/{id}")
    public Optional<User> getUserById(@PathVariable Long id) {
        return userService.getUserById(id);
    }

    @PostMapping
    public User createUser(@RequestBody User user) {
        return userService.createUser(user);
    }

    @DeleteMapping("/{id}")
    public void deleteUser(@PathVariable Long id) {
        userService.deleteUser(id);
    }
}
```
File: src/main/java/com/example/myproject/repository/UserRepository.java