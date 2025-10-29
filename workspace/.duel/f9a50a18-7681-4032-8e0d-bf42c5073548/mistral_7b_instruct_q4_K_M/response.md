I apologize for the confusion. Here is the contents of the attached Java program:
```java
import java.sql.*;
import java.util.ArrayList;
import java.util.List;

public class UserService {
    private Connection connection;

    public UserService(Connection connection) {
        this.connection = connection;
    }

    public List<User> getAllUsers() throws SQLException {
        List<User> users = new ArrayList<>();
        String query = "SELECT * FROM users";
        Statement statement = connection.createStatement();
        ResultSet resultSet = statement.executeQuery(query);

        while (resultSet.next()) {
            int id = resultSet.getInt("id");
            String name = resultSet.getString("name");
            String email = resultSet.getString("email");
            users.add(new User(id, name, email));
        }

        return users;
    }
}
```
Please let me know if you have any questions or need further assistance.