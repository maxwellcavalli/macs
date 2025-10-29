File: src/main/java/com/example/user/UserService.java
```typescript
package com.example.user;

import org.springframework.stereotype.Service;

@Service
public class UserService {
    // Implement methods for querying the user table here
}
```
File: src/main/java/com/example/user/UserController.java
```typescript
package com.example.user;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/users")
public class UserController {
    // Implement methods for handling HTTP requests related to the user table here
}
```
File: src/main/java/com/example/user/UserRepository.java
```typescript
package com.example.user;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface UserRepository extends JpaRepository<User, Long> {
    // Implement methods for querying the user table here
}
```
File: src/main/java/com/example/user/User.java
```typescript
package com.example.user;

import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Id;

@Entity
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    // Getters and setters for other fields here
}
```