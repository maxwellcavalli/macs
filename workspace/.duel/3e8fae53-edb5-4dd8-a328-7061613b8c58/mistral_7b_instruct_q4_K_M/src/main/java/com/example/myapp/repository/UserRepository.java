import com.example.myapp.controller.UserController;
import com.example.myapp.model.User;
import org.springframework.data.r2dbc.repository.R2dbcRepository;
import reactor.core.publisher.Flux;

public interface UserRepository extends R2dbcRepository<User, String> {
    Flux<User> findAll();
}
