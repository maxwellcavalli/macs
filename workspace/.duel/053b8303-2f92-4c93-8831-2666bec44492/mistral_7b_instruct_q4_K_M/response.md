To create a repository, service, and connect it to a controller to query users using R2DBC, you can follow these steps:

1. Create a new Spring Boot project with the following dependencies: Web, JPA, and R2DBC. You can use start.spring.io or your favorite IDE to create the project.
```java
File: src/main/resources/pom.xml
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
1. Create a User entity class that maps to the database table containing user information.
```java
File: src/main/java/com/example/userentity.java
public class UserEntity {
    @Id
    private Long id;
    private String name;
    private String email;

    // getters and setters
}
```
1. Create a UserRepository interface that extends the JpaRepository interface and provides methods for querying users.
```java
File: src/main/java/com/example/userrepository.java
public interface UserRepository extends JpaRepository<UserEntity, Long> {
    List<UserEntity> findAllByEmail(String email);
}
```
1. Create a UserService class that uses the UserRepository to query users and perform other business logic.
```java
File: src/main/java/com/example/userservice.java
public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public List<UserEntity> findAllByEmail(String email) {
        return userRepository.findAllByEmail(email);
    }
}
```
1. Create a UserController class that uses the UserService to handle HTTP requests and responses.
```java
File: src/main/java/com/example/usercontroller.java
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/users")
    public List<UserEntity> getUsersByEmail(@RequestParam String email) {
        return userService.findAllByEmail(email);
    }
}
```
1. Configure the R2DBC connection in the application.properties file.
```java
File: src/main/resources/application.properties
spring.datasource.url=jdbc:postgresql://localhost:5432/mydatabase
spring.datasource.username=myuser
spring.datasource.password=mypassword
spring.jpa.hibernate.ddl-auto=update
```
1. Run the application and test the endpoint by sending a GET request to `http://localhost:8080/users?email=example@example.com`.

That's it! You now have a repository, service, and controller set up to query users using R2DBC in Spring Boot.