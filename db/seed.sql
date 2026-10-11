BEGIN;

INSERT INTO periodicidad_pago (codigo, nombre, factor_mensual, orden) VALUES
('SEMANAL','Semanal',52.0/12.0,1),('QUINCENAL','Quincenal',2,2),('MENSUAL','Mensual',1,3),
('BIMESTRAL','Bimestral',0.5,4),('TRIMESTRAL','Trimestral',1.0/3.0,5),
('SEMESTRAL','Semestral',1.0/6.0,6),('ANUAL','Anual',1.0/12.0,7)
ON CONFLICT DO NOTHING;

INSERT INTO unidad_medida_insumo (codigo, nombre, orden) VALUES
('ML','mL',1),('G','g',2),('MG','mg',3),('PZA','pieza',4),('FRASCO','frasco',5),
('JERINGA','jeringa',6),('CAPSULA','cápsula',7),('ROLLO','rollo',8),('HOJA','hoja',9),
('PAR','par',10),('CAJA','caja',11),('TUBO','tubo',12),('SOBRE','sobre',13),('KIT','kit',14)
ON CONFLICT DO NOTHING;

INSERT INTO especialidad_odontologica (clave, nombre, orden) VALUES
('GENERAL','Odontología general',1),('ENDODONCIA','Endodoncia',2),('ORTODONCIA','Ortodoncia',3),
('PERIODONCIA','Periodoncia',4),('PROSTODONCIA','Prostodoncia',5),('CIRUGIA','Cirugía oral',6),
('ODONTOPEDIATRIA','Odontopediatría',7),('IMPLANTOLOGIA','Implantología',8),
('ESTETICA','Odontología estética',9),('RADIOLOGIA','Radiología dental',10)
ON CONFLICT DO NOTHING;

COMMIT;
