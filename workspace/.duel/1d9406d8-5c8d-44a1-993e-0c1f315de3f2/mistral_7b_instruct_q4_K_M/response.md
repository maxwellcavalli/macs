To create a repository, service, and connect it to a controller to query users using R2DBC, you can follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, and R2DBC. You can use the Spring Initializr (<https://start.spring.io/>) or your favorite IDE to create the project.
2. Define the User entity in your project's model package. This entity should have fields for the user's ID, name, email, and any other relevant information.
3. Create a repository interface that extends the R2dbcRepository interface. This interface will define the methods for querying users using R2DBC.
4. Implement the repository interface with your chosen database driver (e.g., PostgreSQL, MySQL). You can use the Spring Data R2DBC library to simplify this process.
5. Create a service class that uses the repository to perform business logic related to user queries. This class should handle any errors or exceptions that may occur during query execution.
6. Create a controller class that exposes REST endpoints for querying users. The controller should use the service class to execute user queries and return the results as JSON responses.
7. Configure your database connection details in the application.properties file. This file should include the driver, URL, username, and password for your chosen database.
8. Run your Spring Boot application and test the user query endpoints using a tool like Postman or curl.

Here's some sample code to get you started:
```java
// User entity
@Entity
public class User {
    @Id
    private Long id;
    private String name;
    private String email;
    // getters and setters
}

// UserRepository interface
public interface UserRepository extends R2dbcRepository<User, Long> {
    List<User> findAll();
    User findById(Long id);
    // other query methods
}

// UserService class
@Service
public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public List<User> findAllUsers() {
        return userRepository.findAll();
    }

    public User findUserById(Long id) {
        return userRepository.findById(id).orElse(null);
    }
}

// UserController class
@RestController
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/users")
    public List<User> getAllUsers() {
        return userService.findAllUsers();
    }

    @GetMapping("/users/{id}")
    public User getUserById(@PathVariable Long id) {
        return userService.findUserById(id);
    }
}
```