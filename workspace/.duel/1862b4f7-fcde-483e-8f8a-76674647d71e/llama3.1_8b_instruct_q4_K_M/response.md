Let's get started. To confirm, we'll be creating a new implementation to query a user database table using R2DBC for Reactive Java.

Here are the components we'll create:

1. `UserRepository` (R2DBC repository)
2. `UserService` (business logic service)
3. `UserController` (REST controller)

We'll use the standard Maven project structure with the following package organization:
```
com.example
  |- main
    |- java
      |- com
        |- example
          |- UserApplication.java
          |- user
            |- UserRepository.java
            |- UserService.java
            |- UserController.java
```
Before we start, do you have any specific database configuration or connection details I should be aware of?