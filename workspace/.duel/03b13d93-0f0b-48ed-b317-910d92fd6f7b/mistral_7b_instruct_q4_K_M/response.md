File: src/main/java/com/example/myapp/UserService.java
```typescript
package com.example.myapp;

import org.springframework.stereotype.Service;

@Service
public class UserService {
    // Implement methods to query the user table here
}
```
File: src/main/java/com/example/myapp/UserController.java
```typescript
package com.example.myapp;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class UserController {
    @GetMapping("/users")
    public String getUsers(@RequestParam("id") int id) {
        // Query the user table and return results here
    }
}
```
File: src/main/java/com/example/myapp/UserRepository.java
```typescript
package com.example.myapp;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface UserRepository extends JpaRepository<User, Integer> {
    // Implement methods to query the user table here
}
```
File: src/main/java/com/example/myapp/User.java
```typescript
package com.example.myapp;

import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Id;

@Entity
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;
    // Getters and setters for other fields here
}
```