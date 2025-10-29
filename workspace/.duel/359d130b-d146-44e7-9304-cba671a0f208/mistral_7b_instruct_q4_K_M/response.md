To create a repository, service, and connect it to a controller to query users using R2DBC in Spring Boot, follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, R2DBC, and any other required libraries.
2. Define your User entity class with the necessary fields and annotations for JPA to map it to a database table.
3. Create a repository interface that extends `R2dbcRepository<User, String>`. This will provide basic CRUD operations for your User entity.
4. Implement the repository interface in a concrete class that extends `R2dbcRepositoryImpl<User, String>`. In this class, you'll need to configure the R2DBC connection details and set up any necessary mappings between your User entity and the database table.
5. Create a service class that will handle business logic for querying users. This class should use the repository to perform CRUD operations on User entities.
6. Create a controller class that will handle HTTP requests for querying users. This class should use the service to retrieve user data and return it as JSON or another appropriate format.
7. Configure your application to start the Spring Boot server and map the controller endpoint to an HTTP URL.
8. Run your application and test the endpoint using a tool like Postman or curl.

Here's some sample code for a User entity class:
```java
@Entity
public class User {
    @Id
    private String id;
    private String name;
    private int age;

    // getters and setters
}
```
And here's some sample code for a repository interface that extends `R2dbcRepository<User, String>`:
```java
public interface UserRepository extends R2dbcRepository<User, String> {
    List<User> findAll();
    User findById(String id);
    User save(User user);
    void deleteById(String id);
}
```
You can implement this interface in a concrete class like this:
```java
@Repository
public class UserRepositoryImpl extends R2dbcRepositoryImpl<User, String> {
    private final DataSource dataSource;

    public UserRepositoryImpl(DataSource dataSource) {
        super(dataSource);
    }

    @Override
    protected String getTableName() {
        return "users";
    }

    @Override
    protected String getKeyGeneratorName() {
        return "uuid";
    }

    // implement other methods as needed
}
```
Finally, you can create a service class like this:
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

    public User getUserById(String id) {
        return userRepository.findById(id);
    }

    public User saveUser(User user) {
        return userRepository.save(user);
    }

    public void deleteUserById(String id) {
        userRepository.deleteById(id);
    }
}
```
And a controller class like this:
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
    public User getUserById(@PathVariable String id) {
        return userService.getUserById(id);
    }

    @PostMapping
    public User saveUser(@RequestBody User user) {
        return userService.saveUser(user);
    }

    @DeleteMapping("/{id}")
    public void deleteUserById(@PathVariable String id) {
        userService.deleteUserById(id);
    }
}
```
File: src/main/java/com/example/myapp/repository/UserRepositoryImpl.java
```java
@Repository
public class UserRepositoryImpl extends R2dbcRepositoryImpl<User, String> {
    private final DataSource dataSource;

    public UserRepositoryImpl(DataSource dataSource) {
        super(dataSource);
    }

    @Override
    protected String getTableName() {
        return "users";
    }

    @Override
    protected String getKeyGeneratorName() {
        return "uuid";
    }

    // implement other methods as needed
}
```
File: src/main/java/com/example/myapp/service/UserService.java
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

    public User getUserById(String id) {
        return userRepository.findById(id);
    }

    public User saveUser(User user) {
        return userRepository.save(user);
    }

    public void deleteUserById(String id) {
        userRepository.deleteById(id);
    }
}
```
File: src/main/java/com/example/myapp/controller/UserController.java
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
    public User getUserById(@PathVariable String id) {
        return userService.getUserById(id);
    }

    @PostMapping
    public User saveUser(@RequestBody User user) {
        return userService.saveUser(user);
    }

    @DeleteMapping("/{id}")
    public void deleteUserById(@PathVariable String id) {
        userService.deleteUserById(id);
    }
}
```