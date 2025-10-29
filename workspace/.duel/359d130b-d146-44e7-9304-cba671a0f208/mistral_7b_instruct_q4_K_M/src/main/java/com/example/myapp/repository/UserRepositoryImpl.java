package com.example.myapp.repository;

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
