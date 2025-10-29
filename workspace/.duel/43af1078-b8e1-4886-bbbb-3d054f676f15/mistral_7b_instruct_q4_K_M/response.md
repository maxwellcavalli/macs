To create a repository, service, and connect it to a controller to query users using R2DBC, you can follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, and R2DBC. You can do this by using the Spring Initializr (<https://start.spring.io/>) or your favorite IDE.
2. Define the User entity in your project's model package. This entity should have fields for the user's ID, name, email, and any other relevant data.
3. Create a repository interface that extends the R2dbcRepository interface. This interface will define the methods for querying users using R2DBC.
4. Implement the repository interface with your chosen database driver (e.g., PostgreSQL, MySQL, etc.). This implementation should use the R2DBC API to interact with the database and perform CRUD operations on the User entity.
5. Create a service class that will handle business logic for querying users. This class should use the repository to retrieve user data from the database and perform any necessary processing or validation.
6. Create a controller class that will handle HTTP requests for querying users. This controller should use the service to retrieve user data and return it as JSON or another appropriate format.
7. Configure your application to connect to the database by adding the necessary configuration properties in your `application.properties` file. For example, if you are using PostgreSQL, you can add the following properties:
```
spring.datasource.url=jdbc:postgresql://localhost:5432/mydatabase
spring.datasource.username=myuser
spring.datasource.password=mypassword
spring.jpa.hibernate.ddl-auto=update
```
1. Run your application and test the controller by sending an HTTP request to query users. You can use tools like Postman or curl to send the request and verify that the response contains the expected user data.

Here's some sample code for a repository interface:
```java
public interface UserRepository extends R2dbcRepository<User, Long> {
    List<User> findAll();
    User findById(Long id);
    User save(User user);
    void deleteById(Long id);
}
```
And here's some sample code for a service class:
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

    public User getUserById(Long id) {
        return userRepository.findById(id).orElseThrow(() -> new EntityNotFoundException("User not found"));
    }

    public User createUser(User user) {
        return userRepository.save(user);
    }

    public void deleteUser(Long id) {
        userRepository.deleteById(id);
    }
}
```