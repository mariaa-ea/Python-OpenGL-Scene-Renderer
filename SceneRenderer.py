from OpenGL.GL import *
from OpenGL.GLUT import *
import numpy as np
import glm


class SceneRenderer:
    def __init__(self, vertex_code, fragment_code_path, post_process_code_path, 
                 screen_width=500, screen_height=500, initial_fov=120):
        
        # Параметры окна и камеры
        self.cam_pos = glm.vec3(0.0, 0.0, 10.0) #  Позиция камеры
        self.cam_dir = glm.vec3(0.0, 0.0, -1.0) # Направление обзора
        self.cam_up = glm.vec3(0.0, 1.0, 0.0) # Направление вверх
        self.screen_dims = (screen_width, screen_height) # Размер экрана
        self.render_time = 0.01 # Время рендера
        self.fov_angle = glm.radians(initial_fov) # Угол обзора

        # Инициализация для отслеживания изменений
        self.is_paused = False # Флаг для состояния паузы
        self.old_pause_state = False # Флаг для отслеживания изменения состояния паузы
        # Предыдущее состояние
        self.prev_cam_pos = glm.vec3(0.0)
        self.prev_cam_dir = glm.vec3(0.0)
        self.prev_fov = 0.0
        self.prev_time = 0.0       

        # Компиляция и создание шейдерных программ
        self.program_scene = self._init_program(vertex_code, fragment_code_path)
        self.program_postprocess = self._init_program(vertex_code, post_process_code_path)
        self.quad_vao = self._create_quad()
        
        # Накопительная текстура и фреймбуфер
        self.accum_texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.accum_texture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB32F, self.screen_dims[0], self.screen_dims[1], 0, GL_RGB, GL_FLOAT, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        self.frame_buffer = glGenFramebuffers(1)
        glBindFramebuffer(GL_FRAMEBUFFER, self.frame_buffer)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.accum_texture, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

        self.frame_num = 0
        
    def _init_program(self, vertex_code, fragment_code):
        program_id = glCreateProgram()
        v_shader = self._compile_shader(GL_VERTEX_SHADER, vertex_code)
        f_shader = self._compile_shader(GL_FRAGMENT_SHADER, fragment_code)
        
        glAttachShader(program_id, v_shader)
        glAttachShader(program_id, f_shader)
        glLinkProgram(program_id)
        
        status = glGetProgramiv(program_id, GL_LINK_STATUS)
        if status == GL_FALSE:
            strInfoLog = glGetProgramInfoLog(program_id)
            print("Shader link failure: \n", strInfoLog)
        
        glDeleteShader(v_shader)
        glDeleteShader(f_shader)
        
        return program_id

    def _compile_shader(self, shader_type, source):
        shader = glCreateShader(shader_type)
        glShaderSource(shader, source)
        glCompileShader(shader)
        
        status = glGetShaderiv(shader, GL_COMPILE_STATUS)
        if status == GL_FALSE:
            strInfoLog = glGetShaderInfoLog(shader)
            print("Shader compile failure: \n", strInfoLog)
        
        return shader

    def _create_quad(self):
        vertices = np.array([
            -1.0, -1.0, 0.0, 0.0, 0.0,
             1.0, -1.0, 0.0, 1.0, 0.0,
            -1.0,  1.0, 0.0, 0.0, 1.0,

             1.0, -1.0, 0.0, 1.0, 0.0,
             1.0,  1.0, 0.0, 1.0, 1.0,
            -1.0,  1.0, 0.0, 0.0, 1.0,
        ], dtype='float32')
        
        vao = glGenVertexArrays(1)
        glBindVertexArray(vao)
        
        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 5 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 5 * 4, ctypes.c_void_p(3 * 4))
        
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)
        
        return vao
    
    def _render_scene_to_buffer(self, sample_rate):
        # устанавливаю рендер в накопительный фреймбуфер
        glBindFramebuffer(GL_FRAMEBUFFER, self.frame_buffer)
        glUseProgram(self.program_scene)

        # проверяю, не переместилась ли камера или источник света
        camera_moved = glm.any(glm.notEqual(self.prev_cam_pos, self.cam_pos)) or \
                       glm.any(glm.notEqual(self.prev_cam_dir, self.cam_dir)) or \
                       self.prev_fov != self.fov_angle or  self.prev_time != self.render_time

        # при смене состояния паузы, или движения, или  камеры - сбрасываем накопление
        if camera_moved or (self.is_paused != self.old_pause_state and not self.is_paused):
              glClear(GL_COLOR_BUFFER_BIT)
              self.frame_num = 1
             
        # передаю параметры в шейдер
        if self.frame_num > 1:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.accum_texture)
            glUniform1i(glGetUniformLocation(self.program_scene, "prevTexture"), 0)
            glUniform1i(glGetUniformLocation(self.program_scene, "frame"), self.frame_num)
    
        glUniform1i(glGetUniformLocation(self.program_scene, "uSamples"), sample_rate)
        glUniform2f(glGetUniformLocation(self.program_scene, "uViewportSize"), *self.screen_dims)
        glUniform3f(glGetUniformLocation(self.program_scene, "uPosition"), *self.cam_pos)
        glUniform3f(glGetUniformLocation(self.program_scene, "uDirection"), *self.cam_dir)
        glUniform3f(glGetUniformLocation(self.program_scene, "uUp"), *self.cam_up)
        glUniform1f(glGetUniformLocation(self.program_scene, "uFOV"), self.fov_angle)
        glUniform1f(glGetUniformLocation(self.program_scene, "uTime"), self.render_time)
        
        glBindVertexArray(self.quad_vao)
        glDrawArrays(GL_TRIANGLES, 0, 6)
        glBindVertexArray(0)
        glUseProgram(0)

        glBindFramebuffer(GL_FRAMEBUFFER, 0)

        # далее сохраняется текущее состояние для  следующего рендера
        self.prev_cam_pos = self.cam_pos
        self.prev_cam_dir = self.cam_dir
        self.prev_fov = self.fov_angle
        self.prev_time = self.render_time
        self.old_pause_state = self.is_paused
        
        # инкремент времени, если не на паузе
        if not self.is_paused:
            self.render_time += 0.016
        
        self.frame_num += 1

    def _process_and_display(self):
        # отрисовка финального изображения на экран
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glUseProgram(self.program_postprocess)
        
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.accum_texture)
        glUniform1i(glGetUniformLocation(self.program_postprocess, "uImage"), 0)
        glUniform1i(glGetUniformLocation(self.program_postprocess, "uImageSamples"), self.frame_num)
        
        glBindVertexArray(self.quad_vao)
        glDrawArrays(GL_TRIANGLES, 0, 6)
        glBindVertexArray(0)
        glUseProgram(0)


    def render(self):
        sample_count = 32 if not self.is_paused else 1024
        self._render_scene_to_buffer(sample_count)
        self._process_and_display()
    

if __name__ == "__main__":
    glutInit()
    glutInitContextVersion(3, 3)
    glutInitContextProfile(GLUT_CORE_PROFILE)
    glutInitDisplayMode(GLUT_RGBA | GLUT_DOUBLE | GLUT_DEPTH)
    glutInitWindowSize(500, 500)
    glutCreateWindow(b"Scene Renderer")

    with open("shaders/vertex.vert", "r", encoding="utf-8") as f:
        vertex_code = f.read()
    with open("shaders/path_tracing.frag", "r", encoding="utf-8") as f:
        path_tracing_code = f.read()
    with open("shaders/post_process.frag", "r", encoding="utf-8") as f:
        post_process_code = f.read()

    renderer = SceneRenderer(vertex_code, path_tracing_code, post_process_code)

    def display_func():
        renderer.render()
        glutSwapBuffers()

    def update_func(value):
        glutPostRedisplay()
        glutTimerFunc(16, update_func, 0)

    def keyboard_func(key, x, y):
        if key == b' ':
           renderer.is_paused = not renderer.is_paused
        glutPostRedisplay()

    glutDisplayFunc(display_func)
    glEnable(GL_DEPTH_TEST)
    glutTimerFunc(16, update_func, 0)
    glutKeyboardFunc(keyboard_func)

    glutMainLoop()
