File: src/main/java/com/example/user/UserService.java
```typescript
package com.example.user;

import java.util.List;

public interface UserService {
    List<User> getAllUsers();
}
```

File: src/main/java/com/example/user/UserController.java
```typescript
package com.example.user;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/users")
public class UserController {
    @Autowired
    private UserService userService;

    @GetMapping
    public List<User> getAllUsers() {
        return userService.getAllUsers();
    }
}
```

File: src/main/java/com/example/user/UserRepository.java
```typescript
package com.example.user;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface UserRepository extends JpaRepository<User, Long> {
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
    private String name;
    private String email;

    // getters and setters
}
```