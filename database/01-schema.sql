ALTER SESSION SET CONTAINER = FREEPDB1;

CREATE TABLE ticketops.clientes (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome VARCHAR2(120) NOT NULL,
    email VARCHAR2(120) NOT NULL UNIQUE,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    createdby VARCHAR2(120) DEFAULT SYS_CONTEXT('USERENV', 'SESSION_USER') NOT NULL,
    updated TIMESTAMP,
    updatedby VARCHAR2(120)
);

CREATE TABLE ticketops.chamados (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cliente_id NUMBER NOT NULL REFERENCES ticketops.clientes(id),
    titulo VARCHAR2(200) NOT NULL,
    descricao CLOB,
    prioridade CHAR(1) DEFAULT 'M' NOT NULL
        CONSTRAINT ck_chamados_prioridade CHECK (prioridade IN ('B', 'M', 'A', 'C')),
    status CHAR(1) DEFAULT 'A' NOT NULL
        CONSTRAINT ck_chamados_status CHECK (status in ('A', 'E', 'R', 'C')),
    data_resolvido TIMESTAMP,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    createdby VARCHAR2(120) DEFAULT SYS_CONTEXT('USERENV', 'SESSION_USER') NOT NULL,
    updated TIMESTAMP,
    updatedby VARCHAR2(120)
);

CREATE TABLE ticketops.comentarios (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chamado_id NUMBER NOT NULL REFERENCES ticketops.chamados(id),
    autor VARCHAR2(120) NOT NULL,
    texto CLOB NOT NULL,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    createdby VARCHAR2(120) DEFAULT SYS_CONTEXT('USERENV', 'SESSION_USER') NOT NULL,
    updated TIMESTAMP,
    updatedby VARCHAR2(120)
);

CREATE INDEX ticketops.idx_chamados_status ON ticketops.chamados(status);
CREATE INDEX ticketops.idx_chamados_cliente ON ticketops.chamados(cliente_id);
CREATE INDEX ticketops.idx_comentarios_chamado ON ticketops.comentarios(chamado_id);
